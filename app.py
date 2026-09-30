from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'waffle-pos-gizli-anahtar'
# Jinja şablonlarında range() kullanabilmek için:
app.jinja_env.globals.update(range=range)

socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

fiyatlar = {
    'taban_fiyat': 180,
    'ekstra_cikolata': 25,
    'ekstra_meyve': 20,
    'ekstra_susleme': 15
}

gunluk_durum = {
    'gun_acik': True,
    'baslangic_zamani': datetime.now().strftime("%d.%m.%Y %H:%M"),
    'toplam_hasilat': 0,
    'tamamlanan_siparis_sayisi': 0
}

siparisler = []


@app.route('/')
def index():
    masa_no = request.args.get('masa', '1')
    try:
        if not (1 <= int(masa_no) <= 10):
            masa_no = '1'
    except ValueError:
        masa_no = '1'

    aktif_siparisler = [s for s in siparisler if str(s['masa']) == str(masa_no) and s['durum'] == 'Hazırlanıyor']
    return render_template('menu.html', masa_no=masa_no, aktif_siparisler=aktif_siparisler, fiyatlar=fiyatlar,
                           gun_acik=gunluk_durum['gun_acik'])


@app.route('/kasa')
def kasa():
    return render_template('kasa.html', siparisler=siparisler, fiyatlar=fiyatlar, gunluk_durum=gunluk_durum)


@socketio.on('yeni_siparis')
def siparis_al(data):
    if not gunluk_durum['gun_acik']:
        emit('siparis_hata', {'mesaj': 'Kasa şu anda kapalıdır.'})
        return

    siparis_id = len(siparisler) + 1
    tutar = float(data.get('tutar', fiyatlar['taban_fiyat']))

    yeni_siparis = {
        'id': siparis_id,
        'masa': str(data.get('masa')),
        'hamur': data.get('hamur'),
        'cikolatalar': data.get('cikolatalar', []),
        'meyveler': data.get('meyveler', []),
        'suslemeler': data.get('suslemeler', []),
        'not': data.get('not', ''),
        'tutar': tutar,
        'saat': datetime.now().strftime("%H:%M"),
        'durum': 'Hazırlanıyor'
    }
    siparisler.append(yeni_siparis)

    emit('kasaya_bildir', yeni_siparis, broadcast=True)
    emit('masaya_yeni_siparis', yeni_siparis, broadcast=True)


@socketio.on('siparis_tamamla')
def siparis_tamamla(data):
    s_id = data.get('id')
    masa = None
    for s in siparisler:
        if s['id'] == s_id and s['durum'] != 'Teslim Edildi':
            s['durum'] = 'Teslim Edildi'
            masa = s['masa']
            gunluk_durum['toplam_hasilat'] += s['tutar']
            gunluk_durum['tamamlanan_siparis_sayisi'] += 1
            break

    emit('durum_guncellendi', {
        'id': s_id,
        'masa': masa,
        'durum': 'Teslim Edildi',
        'toplam_hasilat': gunluk_durum['toplam_hasilat'],
        'tamamlanan_adet': gunluk_durum['tamamlanan_siparis_sayisi']
    }, broadcast=True)


@socketio.on('fiyat_guncelle')
def fiyat_guncelle(yeni_fiyatlar):
    global fiyatlar
    fiyatlar.update({
        'taban_fiyat': float(yeni_fiyatlar.get('taban_fiyat', 180)),
        'ekstra_cikolata': float(yeni_fiyatlar.get('ekstra_cikolata', 25)),
        'ekstra_meyve': float(yeni_fiyatlar.get('ekstra_meyve', 20)),
        'ekstra_susleme': float(yeni_fiyatlar.get('ekstra_susleme', 15))
    })
    emit('fiyatlar_degisti', fiyatlar, broadcast=True)

@socketio.on('gun_durum_degistir')
def gun_durum_degistir(action):
    global siparisler, gunluk_durum
    try:
        if action == 'bitir':
            gunluk_durum['gun_acik'] = False
            ozet = {
                'toplam_hasilat': gunluk_durum.get('toplam_hasilat', 0),
                'toplam_siparis': gunluk_durum.get('tamamlanan_siparis_sayisi', 0),
                'kapanis_zamani': datetime.now().strftime("%d.%m.%Y %H:%M")
            }
            emit('gun_kapandi', ozet, broadcast=True)
        elif action == 'baslat':
            gunluk_durum['gun_acik'] = True
            gunluk_durum['toplam_hasilat'] = 0
            gunluk_durum['tamamlanan_siparis_sayisi'] = 0
            gunluk_durum['baslangic_zamani'] = datetime.now().strftime("%d.%m.%Y %H:%M")
            siparisler.clear()
            emit('gun_basladi', gunluk_durum, broadcast=True)
    except Exception as e:
        print(f"Gün durum hatası: {e}")


if __name__ == '__main__':
    socketio.run(app, host='127.0.0.1', port=5000, debug=True, allow_unsafe_werkzeug=True)

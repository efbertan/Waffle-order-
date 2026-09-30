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

function gunDurum(action) {
    const mesaj = action === 'bitir' ? "Günü sonlandırmak istiyor musunuz?" : "Yeni gün başlatılsın mı?";
    if (confirm(mesaj)) {
      socket.emit("gun_durum_degistir", action);
    }
  }

  socket.on("gun_kapandi", function(ozet) {
    const btnBitir = document.getElementById("gunSonuBtn");
    const btnBaslat = document.getElementById("gunBaslatBtn");
    if (btnBitir) btnBitir.style.display = "none";
    if (btnBaslat) btnBaslat.style.display = "inline-block";
    
    alert("Gün başarıyla kapatıldı!\n\nToplam Hasılat: " + ozet.toplam_hasilat + " ₺\nTamamlanan Sipariş: " + ozet.toplam_siparis);
  });

  socket.on("gun_basladi", function(data) {
    const btnBitir = document.getElementById("gunSonuBtn");
    const btnBaslat = document.getElementById("gunBaslatBtn");
    if (btnBitir) btnBitir.style.display = "inline-block";
    if (btnBaslat) btnBaslat.style.display = "none";
    
    document.getElementById("totalRevenue").innerText = "0";
    document.getElementById("totalOrders").innerText = "0";
    document.getElementById("ordersGrid").innerHTML = "";
    
    alert("Yeni gün başlatıldı, menü siparişlere yeniden açıldı!");
  });


if __name__ == '__main__':
    socketio.run(app, host='127.0.0.1', port=5000, debug=True, allow_unsafe_werkzeug=True)

import csv
import io
import json
from datetime import datetime
from flask import Flask, render_template, request, session, redirect, url_for, make_response, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'waffle-gizli-anahtar-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///waffle.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

KASA_PIN = "1234"

VARSAYILAN_FIYATLAR = {
    "taban_fiyat": 150,
    "ekstra_meyve": 25,
    "ekstra_cikolata": 25,
    "ekstra_susleme": 15
}

# --- VERİTABANI MODELLERİ ---
class Siparis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    masa = db.Column(db.String(20), nullable=False)
    hamur = db.Column(db.String(50))
    cikolatalar = db.Column(db.Text)
    meyveler = db.Column(db.Text)
    suslemeler = db.Column(db.Text)
    notlar = db.Column(db.Text)
    fiyat = db.Column(db.Float, default=0.0)
    durum = db.Column(db.String(30), default="Hazırlanıyor")
    tarih = db.Column(db.DateTime, default=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "masa": self.masa,
            "hamur": self.hamur,
            "cikolatalar": json.loads(self.cikolatalar) if self.cikolatalar else [],
            "meyveler": json.loads(self.meyveler) if self.meyveler else [],
            "suslemeler": json.loads(self.suslemeler) if self.suslemeler else [],
            "notlar": self.notlar,
            "fiyat": self.fiyat,
            "durum": self.durum,
            "tarih": self.tarih.strftime("%H:%M")
        }

class Urun(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    kategori = db.Column(db.String(30), nullable=False)  # hamur, cikolata, meyve, susleme
    ad = db.Column(db.String(100), nullable=False)
    aktif = db.Column(db.Boolean, default=True)

    def to_dict(self):
        return {"id": self.id, "kategori": self.kategori, "ad": self.ad, "aktif": self.aktif}

class Ayar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    anahtar = db.Column(db.String(50), unique=True, nullable=False)
    deger = db.Column(db.Text, nullable=False)

def ayar_getir(anahtar):
    ayar = Ayar.query.filter_by(anahtar=anahtar).first()
    if ayar:
        try:
            return json.loads(ayar.deger)
        except Exception:
            return ayar.deger
    if anahtar == 'fiyatlar':
        return VARSAYILAN_FIYATLAR
    if anahtar == 'gunluk_durum':
        return {"acik": True, "mesaj": "Siparişler açık"}
    return None

def ayar_kaydet(anahtar, deger):
    ayar = Ayar.query.filter_by(anahtar=anahtar).first()
    deger_str = json.dumps(deger, ensure_ascii=False) if isinstance(deger, (dict, list, bool)) else str(deger)
    if not ayar:
        ayar = Ayar(anahtar=anahtar, deger=deger_str)
        db.session.add(ayar)
    else:
        ayar.deger = deger_str
    db.session.commit()

# Başlangıç ürünlerini otomatik ekleme
def varsayilan_urunleri_yukle():
    if Urun.query.count() == 0:
        varsayilanlar = [
            # Hamur
            ("hamur", "Klasik Çıtır"),
            ("hamur", "Kakaolu Hamur"),
            # Çikolata
            ("cikolata", "Sütlü Çikolata"),
            ("cikolata", "Beyaz Çikolata"),
            ("cikolata", "Bitter Çikolata"),
            ("cikolata", "Karamel Sosu"),
            ("cikolata", "Antep Fıstık Ezmesi"),
            # Meyve
            ("meyve", "Çilek 🍓"),
            ("meyve", "Muz 🍌"),
            ("meyve", "Kivi 🥝"),
            ("meyve", "Yaban Mersini 🫐"),
            ("meyve", "Ananas 🍍"),
            # Süsleme
            ("susleme", "Fındık"),
            ("susleme", "Antep Fıstığı"),
            ("susleme", "Hindistan Cevizi"),
            ("susleme", "Renkli Draje"),
            ("susleme", "Oreo Kırıntısı"),
            ("susleme", "Pudra Şekeri")
        ]
        for kat, ad in varsayilanlar:
            db.session.add(Urun(kategori=kat, ad=ad, aktif=True))
        db.session.commit()

with app.app_context():
    db.create_all()
    varsayilan_urunleri_yukle()

# --- 1. MÜŞTERİ MENÜ EKRANI ---
@app.route('/')
def menu():
    masa = request.args.get('masa')
    fiyatlar = ayar_getir('fiyatlar')
    gunluk_durum = ayar_getir('gunluk_durum')
    urunler = Urun.query.filter_by(aktif=True).all()
    
    kategorize_urunler = {
        "hamur": [u for u in urunler if u.kategori == 'hamur'],
        "cikolata": [u for u in urunler if u.kategori == 'cikolata'],
        "meyve": [u for u in urunler if u.kategori == 'meyve'],
        "susleme": [u for u in urunler if u.kategori == 'susleme']
    }
    return render_template('menu.html', masa=masa, fiyatlar=fiyatlar, gunluk_durum=gunluk_durum, urunler=kategorize_urunler)

# --- 2. KASA & ŞİFRE ROTALARI ---
@app.route('/kasa-giris', methods=['GET', 'POST'])
def kasa_giris():
    hata = None
    if request.method == 'POST':
        girilen_pin = request.form.get('pin', '').strip()
        if girilen_pin == KASA_PIN:
            session['kasa_yetkili'] = True
            return redirect(url_for('kasa'))
        else:
            hata = "Hatalı PIN kodu! Lütfen tekrar deneyin."
    return render_template('kasa_giris.html', hata=hata)

@app.route('/kasa-cikis')
def kasa_cikis():
    session.pop('kasa_yetkili', None)
    return redirect(url_for('kasa_giris'))

@app.route('/kasa')
def kasa():
    if not session.get('kasa_yetkili'):
        return redirect(url_for('kasa_giris'))

    fiyatlar = ayar_getir('fiyatlar')
    gunluk_durum = ayar_getir('gunluk_durum')
    
    tum_db_siparisler = Siparis.query.order_by(Siparis.id.desc()).all()
    siparisler = [s.to_dict() for s in tum_db_siparisler]
    tum_urunler = Urun.query.order_by(Urun.id.asc()).all()

    toplam_hasilat = sum(s.fiyat for s in tum_db_siparisler)
    toplam_adet = len(tum_db_siparisler)
    bekleyen_adet = len([s for s in tum_db_siparisler if s.durum != 'Tamamlandı'])

    return render_template('kasa.html',
                           siparisler=siparisler,
                           fiyatlar=fiyatlar,
                           gunluk_durum=gunluk_durum,
                           toplam_hasilat=toplam_hasilat,
                           toplam_adet=toplam_adet,
                           bekleyen_adet=bekleyen_adet,
                           urunler=tum_urunler)

# Gün Sonu / Başlatma API
@app.route('/api/gun-durum', methods=['POST'])
def api_gun_durum():
    if not session.get('kasa_yetkili'):
        return jsonify({"success": False, "error": "Yetkisiz"}), 403
    
    data = request.get_json() or {}
    acik = data.get('acik', True)
    yeni_durum = {
        "acik": acik,
        "mesaj": "Siparişler açık" if acik else "Bugünlük sipariş alımı durdurulmuştur."
    }
    ayar_kaydet('gunluk_durum', yeni_durum)
    socketio.emit('gun_durumu_guncellendi', yeni_durum)
    return jsonify({"success": True, "durum": yeni_durum})

# --- ÜRÜN YÖNETİMİ API'LERİ ---
@app.route('/api/urun-ekle', methods=['POST'])
def api_urun_ekle():
    if not session.get('kasa_yetkili'):
        return jsonify({"success": False, "error": "Yetkisiz"}), 403
    data = request.get_json() or {}
    kategori = data.get('kategori')
    ad = data.get('ad', '').strip()
    if not kategori or not ad:
        return jsonify({"success": False, "error": "Kategori ve isim zorunludur"}), 400
    
    yeni_urun = Urun(kategori=kategori, ad=ad, aktif=True)
    db.session.add(yeni_urun)
    db.session.commit()
    return jsonify({"success": True, "urun": yeni_urun.to_dict()})

@app.route('/api/urun-duzenle', methods=['POST'])
def api_urun_duzenle():
    if not session.get('kasa_yetkili'):
        return jsonify({"success": False, "error": "Yetkisiz"}), 403
    data = request.get_json() or {}
    urun_id = data.get('id')
    yeni_ad = data.get('ad', '').strip()
    
    urun = Urun.query.get(urun_id)
    if not urun:
        return jsonify({"success": False, "error": "Ürün bulunamadı"}), 404
    
    if yeni_ad:
        urun.ad = yeni_ad
        db.session.commit()
        return jsonify({"success": True, "urun": urun.to_dict()})
    return jsonify({"success": False, "error": "Geçersiz isim"}), 400

@app.route('/api/urun-sil', methods=['POST'])
def api_urun_sil():
    if not session.get('kasa_yetkili'):
        return jsonify({"success": False, "error": "Yetkisiz"}), 403
    data = request.get_json() or {}
    urun_id = data.get('id')
    urun = Urun.query.get(urun_id)
    if urun:
        db.session.delete(urun)
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Ürün bulunamadı"}), 404

# --- 3. EXCEL / CSV İNDİRME ---
@app.route('/admin/siparisler-indir')
def siparisler_indir():
    tum_siparisler = Siparis.query.order_by(Siparis.id.asc()).all()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Siparis ID', 'Masa', 'Fiyat', 'Durum', 'Saat', 'Hamur', 'Cikolatalar', 'Meyveler', 'Suslemeler', 'Not'])
    for s in tum_siparisler:
        cw.writerow([s.id, s.masa, s.fiyat, s.durum, s.tarih.strftime("%d.%m.%Y %H:%M"), s.hamur, s.cikolatalar, s.meyveler, s.suslemeler, s.notlar])
    
    cikti = make_response(si.getvalue().encode('utf-8-sig'))
    cikti.headers["Content-Disposition"] = "attachment; filename=waffle_siparisler.csv"
    cikti.headers["Content-type"] = "text/csv; charset=utf-8"
    return cikti

# --- 4. SOCKET.IO İŞLEMLERİ ---
@socketio.on('yeni_siparis')
def siparis_geldi(data):
    yeni = Siparis(
        masa=str(data.get('masa', '1')),
        hamur=data.get('hamur', ''),
        cikolatalar=json.dumps(data.get('cikolatalar', []), ensure_ascii=False),
        meyveler=json.dumps(data.get('meyveler', []), ensure_ascii=False),
        suslemeler=json.dumps(data.get('suslemeler', []), ensure_ascii=False),
        notlar=data.get('notlar', ''),
        fiyat=float(data.get('fiyat', 0.0)),
        durum="Hazırlanıyor"
    )
    db.session.add(yeni)
    db.session.commit()
    emit('kasa_yeni_siparis', yeni.to_dict(), broadcast=True)

@socketio.on('siparis_durum_guncelle')
def durum_guncelle(data):
    sip_id = data.get('id')
    yeni_durum = data.get('durum')
    sip = Siparis.query.get(sip_id)
    if sip:
        sip.durum = yeni_durum
        db.session.commit()
        emit('siparis_guncellendi', {"id": sip_id, "durum": yeni_durum}, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, debug=True)

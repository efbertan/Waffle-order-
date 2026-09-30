import os
import json
from datetime import datetime
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SECRET_KEY'] = 'waffle_gizli_anahtar_123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///waffle.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Jinja2 için range fonksiyonunu ekle
app.jinja_env.globals.update(range=range)

# --- VERİTABANI MODELLERİ ---
class Siparis(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    masa = db.Column(db.String(10), nullable=False)
    hamur = db.Column(db.String(50), nullable=False)
    cikolatalar = db.Column(db.Text, default="[]")  # JSON string
    meyveler = db.Column(db.Text, default="[]")     # JSON string
    suslemeler = db.Column(db.Text, default="[]")   # JSON string
    not_bilgisi = db.Column(db.String(255), default="")
    tutar = db.Column(db.Float, nullable=False)
    durum = db.Column(db.String(30), default="Hazırlanıyor")
    saat = db.Column(db.String(20), nullable=False)
    tarih = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'masa': self.masa,
            'hamur': self.hamur,
            'cikolatalar': json.loads(self.cikolatalar),
            'meyveler': json.loads(self.meyveler),
            'suslemeler': json.loads(self.suslemeler),
            'not': self.not_bilgisi,
            'tutar': self.tutar,
            'durum': self.durum,
            'saat': self.saat
        }

class Ayar(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    anahtar = db.Column(db.String(50), unique=True, nullable=False)
    deger = db.Column(db.Text, nullable=False)

# Tabloları oluştur ve varsayılan ayarları yükle
with app.app_context():
    db.create_all()
    
    # Fiyat ayarları kontrol
    if not Ayar.query.filter_by(anahtar='fiyatlar').first():
        varsayilan_fiyatlar = {
            'taban_fiyat': 150,
            'ekstra_cikolata': 25,
            'ekstra_meyve': 20,
            'ekstra_susleme': 15
        }
        db.session.add(Ayar(anahtar='fiyatlar', deger=json.dumps(varsayilan_fiyatlar)))
    
    # Günlük durum kontrol
    if not Ayar.query.filter_by(anahtar='gunluk_durum').first():
        varsayilan_durum = {
            'gun_acik': True,
            'toplam_hasilat': 0,
            'tamamlanan_siparis_sayisi': 0
        }
        db.session.add(Ayar(anahtar='gunluk_durum', deger=json.dumps(varsayilan_durum)))
    
    db.session.commit()

def ayar_getir(anahtar):
    ayar = Ayar.query.filter_by(anahtar=anahtar).first()
    return json.loads(ayar.deger) if ayar else {}

def ayar_kaydet(anahtar, veri):
    ayar = Ayar.query.filter_by(anahtar=anahtar).first()
    if ayar:
        ayar.deger = json.dumps(veri)
    else:
        ayar = Ayar(anahtar=anahtar, deger=json.dumps(veri))
        db.session.add(ayar)
    db.session.commit()

# --- ROUTES ---
@app.route('/')
def index():
    masa_no = request.args.get('masa', '1')
    fiyatlar = ayar_getir('fiyatlar')
    gunluk_durum = ayar_getir('gunluk_durum')

    aktif_db_siparisler = Siparis.query.filter_by(masa=str(masa_no)).order_by(Siparis.id.desc()).all()
    aktif_siparisler = [s.to_dict() for s in aktif_db_siparisler]

    return render_template('menu.html',
                           masa_no=masa_no,
                           aktif_siparisler=aktif_siparisler,
                           fiyatlar=fiyatlar,
                           gun_acik=gunluk_durum.get('gun_acik', True))

@app.route('/kasa')
def kasa():
    fiyatlar = ayar_getir('fiyatlar')
    gunluk_durum = ayar_getir('gunluk_durum')
    
    tum_db_siparisler = Siparis.query.order_by(Siparis.id.asc()).all()
    siparisler = [s.to_dict() for s in tum_db_siparisler]

    return render_template('kasa.html',
                           siparisler=siparisler,
                           fiyatlar=fiyatlar,
                           gunluk_durum=gunluk_durum)

# --- SOCKET EVENTS ---
@socketio.on('yeni_siparis')
def handle_yeni_siparis(data):
    gunluk_durum = ayar_getir('gunluk_durum')
    if not gunluk_durum.get('gun_acik', True):
        return

    yeni = Siparis(
        masa=str(data.get('masa', '1')),
        hamur=data.get('hamur', 'Klasik'),
        cikolatalar=json.dumps(data.get('cikolatalar', [])),
        meyveler=json.dumps(data.get('meyveler', [])),
        suslemeler=json.dumps(data.get('suslemeler', [])),
        not_bilgisi=data.get('not', ''),
        tutar=float(data.get('tutar', 0)),
        durum="Hazırlanıyor",
        saat=datetime.now().strftime("%H:%M")
    )
    db.session.add(yeni)
    db.session.commit()

    siparis_dict = yeni.to_dict()
    emit('kasaya_bildir', siparis_dict, broadcast=True)
    emit('masaya_yeni_siparis', siparis_dict, broadcast=True)

@socketio.on('siparis_tamamla')
def handle_siparis_tamamla(data):
    siparis_id = data.get('id')
    siparis = Siparis.query.get(siparis_id)
    if siparis and siparis.durum != "Teslim Edildi":
        siparis.durum = "Teslim Edildi"
        
        gunluk_durum = ayar_getir('gunluk_durum')
        gunluk_durum['toplam_hasilat'] = round(gunluk_durum.get('toplam_hasilat', 0) + siparis.tutar, 2)
        gunluk_durum['tamamlanan_siparis_sayisi'] = gunluk_durum.get('tamamlanan_siparis_sayisi', 0) + 1
        ayar_kaydet('gunluk_durum', gunluk_durum)
        
        db.session.commit()

        emit('durum_guncellendi', {
            'id': siparis.id,
            'toplam_hasilat': gunluk_durum['toplam_hasilat'],
            'tamamlanan_adet': gunluk_durum['tamamlanan_siparis_sayisi']
        }, broadcast=True)

@socketio.on('fiyat_guncelle')
def handle_fiyat_guncelle(data):
    fiyatlar = {
        'taban_fiyat': float(data['taban_fiyat']),
        'ekstra_cikolata': float(data['ekstra_cikolata']),
        'ekstra_meyve': float(data['ekstra_meyve']),
        'ekstra_susleme': float(data['ekstra_susleme'])
    }
    ayar_kaydet('fiyatlar', fiyatlar)
    emit('fiyatlar_degisti', fiyatlar, broadcast=True)

@socketio.on('gun_durum_degistir')
def handle_gun_durum_degistir(action):
    gunluk_durum = ayar_getir('gunluk_durum')
    try:
        if action == 'bitir':
            gunluk_durum['gun_acik'] = False
            ayar_kaydet('gunluk_durum', gunluk_durum)
            ozet = {
                'toplam_hasilat': gunluk_durum.get('toplam_hasilat', 0),
                'toplam_siparis': gunluk_durum.get('tamamlanan_siparis_sayisi', 0)
            }
            emit('gun_kapandi', ozet, broadcast=True)
        elif action == 'baslat':
            gunluk_durum['gun_acik'] = True
            gunluk_durum['toplam_hasilat'] = 0
            gunluk_durum['tamamlanan_siparis_sayisi'] = 0
            ayar_kaydet('gunluk_durum', gunluk_durum)
            
            # İsteğe bağlı: Yeni gün başlayınca eski siparişleri temizlemek veya arşivlemek
            # Siparis.query.delete()  # Eski siparişleri silmek istersen açabilirsin
            # db.session.commit()
            
            emit('gun_basladi', gunluk_durum, broadcast=True)
    except Exception as e:
        print(f"Hata: {e}")

if __name__ == '__main__':
    socketio.run(app, debug=True)

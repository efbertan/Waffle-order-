import csv
import io
import json
from datetime import datetime
from flask import Flask, render_template, request, session, redirect, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'waffle-gizli-anahtar-123'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///waffle.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
socketio = SocketIO(app, cors_allowed_origins="*")

KASA_PIN = "1234"

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

with app.app_context():
    db.create_all()

# --- 1. MÜŞTERİ MENÜ EKRANI (SİPARİŞ VERME EKRANI) ---
@app.route('/')
def menu():
    masa = request.args.get('masa', '1')
    return render_template('menu.html', masa=masa)

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
    
    tum_siparisler = Siparis.query.order_by(Siparis.id.asc()).all()
    siparis_listesi = [s.to_dict() for s in tum_siparisler]
    return render_template('kasa.html', siparisler=siparis_listesi)

# --- 3. EXCEL / CSV İNDİRME ---
@app.route('/admin/siparisler-indir')
def siparisler_indir():
    tum_siparisler = Siparis.query.order_by(Siparis.id.asc()).all()
    
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Siparis ID', 'Masa', 'Fiyat', 'Durum', 'Saat', 'Hamur', 'Cikolatalar', 'Meyveler', 'Suslemeler', 'Not'])
    
    for s in tum_siparisler:
        cw.writerow([
            s.id,
            s.masa,
            s.fiyat,
            s.durum,
            s.tarih.strftime("%d.%m.%Y %H:%M"),
            s.hamur,
            s.cikolatalar,
            s.meyveler,
            s.suslemeler,
            s.notlar
        ])
    
    cikti = make_response(si.getvalue().encode('utf-8-sig'))
    cikti.headers["Content-Disposition"] = "attachment; filename=waffle_siparisler.csv"
    cikti.headers["Content-type"] = "text/csv; charset=utf-8"
    return cikti

# --- 4. SOCKET.IO SİPARİŞ İLETİŞİMİ ---
@socketio.on('yeni_siparis')
def siparis_geldi(data):
    yeni = Siparis(
        masa=data.get('masa', '1'),
        hamur=data.get('hamur', ''),
        cikolatalar=json.dumps(data.get('cikolatalar', []), ensure_ascii=False),
        meyveler=json.dumps(data.get('meyveler', []), ensure_ascii=False),
        suslemeler=json.dumps(data.get('suslemeler', []), ensure_ascii=False),
        notlar=data.get('notlar', ''),
        fiyat=data.get('fiyat', 0.0),
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

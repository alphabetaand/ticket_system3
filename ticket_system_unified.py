import os
import logging
import psycopg2
from flask import Flask, request, jsonify, render_template_string, send_file, make_response, session
from flask_cors import CORS
from passlib.context import CryptContext
from docx import Document
from io import BytesIO
from datetime import datetime
import hashlib
import base64

# QR Code generation
try:
    import qrcode
except ImportError:
    qrcode = None

# Barcode generation
try:
    import barcode
    from barcode.writer import ImageWriter
except ImportError:
    barcode = None

from sqlalchemy import create_engine, Column, Integer, String, DateTime, func, Float, ForeignKey, Boolean, Text
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy import and_, or_

# Configuration
QR_FOLDER = "qrcodes/"
DATABASE_URL = os.getenv("DATABASE_URL")
print("✅ Connexion à :", DATABASE_URL)

# Test connexion simple
try:
    conn = psycopg2.connect(DATABASE_URL)
    print("✅ Connexion PostgreSQL réussie !")
    conn.close()
except Exception as e:
    print("❌ Échec de la connexion :", e)

engine = create_engine(DATABASE_URL, echo=False)
Base = declarative_base()
SessionLocal = sessionmaker(bind=engine)
ADMIN_PASSWORD = "alphonse2000"
FLASK_PORT = 5000
MAX_HISTORY_ENTRIES = 50
SERVICE_FEE_RATE = 0.01
DEFAULT_CODE_TYPE = "qr"

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sécurité
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], default="pbkdf2_sha256", pbkdf2_sha256__default_rounds=30000)
ADMIN_PASSWORD_HASH = pwd_context.hash(ADMIN_PASSWORD)

# Create folders
os.makedirs(QR_FOLDER, exist_ok=True)

# ==============================================
# ETAPE 1 : modèle de vente de billets en ligne
# ==============================================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False, index=True)
    username = Column(String, unique=True, nullable=True, index=True)
    full_name = Column(String, default="")
    phone = Column(String, default="")
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, default=False)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    orders = relationship("Order", back_populates="user")
    tickets = relationship("Ticket", back_populates="buyer")


class Event(Base):
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text, default="")
    location = Column(String, default="")
    date = Column(DateTime, nullable=False)
    category = Column(String, default="concert")
    image_url = Column(String, default="")
    base_price = Column(Float, nullable=False, default=0.0)
    total_capacity = Column(Integer, default=100)
    available_quantity = Column(Integer, default=100)
    is_active = Column(Boolean, default=True)
    code_type = Column(String, default=DEFAULT_CODE_TYPE)  # qr / barcode / both
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    tickets = relationship("Ticket", back_populates="event")
    order_items = relationship("OrderItem", back_populates="event")


class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    order_number = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total_amount = Column(Float, nullable=False, default=0.0)
    fee_amount = Column(Float, nullable=False, default=0.0)
    status = Column(String, default="pending")
    payment_method = Column(String, default="")
    payment_provider = Column(String, default="")
    payer_name = Column(String, default="")
    payer_phone = Column(String, default="")
    payment_reference = Column(String, default="")
    payment_status = Column(String, default="pending")
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=func.now())
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="orders")
    items = relationship("OrderItem", back_populates="order")
    tickets = relationship("Ticket", back_populates="order")


class OrderItem(Base):
    __tablename__ = "order_items"
    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    quantity = Column(Integer, nullable=False, default=1)
    unit_price = Column(Float, nullable=False, default=0.0)
    total_price = Column(Float, nullable=False, default=0.0)

    order = relationship("Order", back_populates="items")
    event = relationship("Event", back_populates="order_items")


class Ticket(Base):
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True, index=True)
    ticket_number = Column(String, unique=True, nullable=False, index=True)
    barcode_value = Column(String, unique=True, nullable=True, index=True)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, default='paid')
    code_type = Column(String, default=DEFAULT_CODE_TYPE)  # qr / barcode / both
    qr_hash = Column(String, nullable=True)
    qr_data = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=func.now())
    scanned_at = Column(DateTime, nullable=True)
    scanned_by = Column(String, default="")
    scan_location = Column(String, default="")

    event = relationship("Event", back_populates="tickets")
    order = relationship("Order", back_populates="tickets")
    buyer = relationship("User", back_populates="tickets")


def init_db():
    Base.metadata.create_all(bind=engine)


def seed_demo_events():
    db = SessionLocal()
    count = db.query(Event).count()
    if count == 0:
        db.add_all([
            Event(
                title="Concert Live Night",
                description="Soirée musicale en plein air avec artistes locaux et internationaux.",
                location="Dakar, Sénégal",
                date=datetime(2026, 11, 15, 20, 0),
                category="concert",
                image_url="",
                base_price=15000.0,
                total_capacity=500,
                available_quantity=500,
                is_active=True,
                code_type="qr",
            ),
            Event(
                title="Festival Culture & Arts",
                description="Festival de musique, danse et arts visuels dans un cadre culturel.",
                location="Saint-Louis, Sénégal",
                date=datetime(2026, 12, 02, 18, 30),
                category="festival",
                image_url="",
                base_price=12000.0,
                total_capacity=300,
                available_quantity=300,
                is_active=True,
                code_type="barcode",
            ),
            Event(
                title="Match de Gala",
                description="Rencontre sportive de gala avec tribunes et zones VIP.",
                location="Thiès, Sénégal",
                date=datetime(2026, 12, 20, 19, 0),
                category="sport",
                image_url="",
                base_price=18000.0,
                total_capacity=250,
                available_quantity=250,
                is_active=True,
                code_type="both",
            ),
        ])
        db.commit()
    db.close()


init_db()
seed_demo_events()

# ==============================================
# ETAPE 5 : Génération QR codes OU codes-barres
# ==============================================

def sanitize_code_type(value):
    code = str(value or DEFAULT_CODE_TYPE).strip().lower()
    if code not in ("qr", "barcode", "both"):
        return DEFAULT_CODE_TYPE
    return code


def generate_barcode_value(ticket_id, order_id):
    unique_str = f"{order_id:06d}{ticket_id:06d}"
    return unique_str[:12]


def generate_qr_code_data(ticket_number, event_id, barcode_value):
    return f"TICKET:{ticket_number}|EVENT:{event_id}|CODE:{barcode_value}|SCAN_ME"


def generate_qr_image(ticket_number, barcode_value, event_id):
    if not qrcode:
        return None
    try:
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr_data = generate_qr_code_data(ticket_number, event_id, barcode_value)
        qr.add_data(qr_data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffered = BytesIO()
        img.save(buffered, format="PNG")
        buffered.seek(0)
        return "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode()
    except Exception:
        return None


def generate_barcode_image(barcode_value, ticket_number):
    if not barcode:
        return None
    try:
        barcode_class = barcode.get_barcode_class('ean13')
        barcode_instance = barcode_class(barcode_value + '1', writer=ImageWriter())
        buffered = BytesIO()
        barcode_instance.write(buffered)
        buffered.seek(0)
        return "data:image/png;base64," + base64.b64encode(buffered.getvalue()).decode()
    except Exception:
        return None


# the rest of the file is same, but event creation and checkout use event.code_type instead of request code_type
# key modifications are below

# In /api/events payload and /api/admin/events response include code_type
# In /api/cart/checkout use event.code_type for the generated Ticket
# In /api/admin/events POST accept code_type and validate it.
# In ticket_details, generate only requested event code_type.

# =====================================================
# route: /api/events
# =====================================================

@app.route('/api/events', methods=['GET'])
def api_events():
    try:
        db = SessionLocal()
        events = db.query(Event).filter(Event.is_active == True).order_by(Event.date.asc()).all()
        db.close()
        payload = [{
            "id": e.id,
            "title": e.title,
            "description": e.description,
            "location": e.location,
            "date": e.date.isoformat() if e.date else None,
            "category": e.category,
            "base_price": float(e.base_price),
            "total_capacity": e.total_capacity,
            "available_quantity": e.available_quantity,
            "code_type": e.code_type,
        } for e in events]
        return jsonify(payload), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =====================================================
# route: /api/cart/checkout
# =====================================================

@app.route('/api/cart/checkout', methods=['POST'])
def cart_checkout():
    try:
        cart = get_cart()
        if not cart:
            return jsonify({"error": "Panier vide"}), 400

        items, subtotal, fee, total = get_cart_items()
        if not items:
            return jsonify({"error": "Aucun billet valide dans le panier"}), 400

        data = request.get_json() or {}
        payment_provider = data.get('payment_provider', 'wave')
        payer_name = str(data.get('payer_name', '')).strip()
        payer_phone = str(data.get('payer_phone', '')).strip()
        payment_reference = str(data.get('payment_reference', '')).strip()

        if not payer_name or not payer_phone:
            return jsonify({"error": "Le nom et le téléphone du client sont requis"}), 400

        provider_valid = payment_provider in ('wave', 'orange')
        if not provider_valid:
            return jsonify({"error": "Opérateur de paiement invalide"}), 400

        if not payment_reference:
            payment_reference = f"{payment_provider.upper()}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        db = SessionLocal()
        order_number = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        demo_user = db.query(User).filter(User.email == "client@ticketshop.sn").first()
        if not demo_user:
            demo_user = User(
                email="client@ticketshop.sn",
                username="client",
                full_name=payer_name,
                phone=payer_phone,
                password_hash=pwd_context.hash("client123"),
                is_admin=False,
            )
            db.add(demo_user)
            db.flush()

        order = Order(
            order_number=order_number,
            user_id=demo_user.id,
            total_amount=round(total, 2),
            fee_amount=round(fee, 2),
            status='paid',
            payment_method='mobile_money',
            payment_provider=payment_provider,
            payer_name=payer_name,
            payer_phone=payer_phone,
            payment_reference=payment_reference,
            payment_status='paid',
            paid_at=datetime.now(),
        )
        db.add(order)
        db.flush()

        for item in items:
            event = db.query(Event).filter(Event.id == item['event_id']).first()
            if not event:
                continue

            db.add(OrderItem(
                order_id=order.id,
                event_id=item['event_id'],
                quantity=item['quantity'],
                unit_price=item['unit_price'],
                total_price=item['total'],
            ))

            event.available_quantity = max(0, event.available_quantity - item['quantity'])

            for i in range(item['quantity']):
                ticket_number = f"TKT-{order.id}-{i+1}"
                barcode_value = generate_barcode_value(i+1, order.id)
                qr_data = generate_qr_code_data(ticket_number, event.id, barcode_value)
                event_code_type = sanitize_code_type(event.code_type)

                ticket = Ticket(
                    ticket_number=ticket_number,
                    barcode_value=barcode_value,
                    event_id=event.id,
                    order_id=order.id,
                    buyer_id=demo_user.id,
                    status='paid',
                    code_type=event_code_type,
                    qr_hash=hashlib.sha256(qr_data.encode()).hexdigest(),
                    qr_data=qr_data,
                )
                db.add(ticket)

        db.commit()
        db.close()

        session['cart'] = {}
        return jsonify({
            "ok": True,
            "order_number": order_number,
            "payment_provider": payment_provider,
            "payer_name": payer_name,
            "payer_phone": payer_phone,
            "payment_reference": payment_reference,
            "total": round(total, 2),
            "fee": round(fee, 2),
            "status": "paid",
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =====================================================
# route: /api/admin/events
# =====================================================

@app.route('/api/admin/events', methods=['GET', 'POST'])
def admin_events():
    try:
        data = request.get_json(silent=True) or {}
        password = request.args.get('password') or data.get('password')
        if not password or not pwd_context.verify(password, ADMIN_PASSWORD_HASH):
            return jsonify({"error": "Accès refusé"}), 401

        db = SessionLocal()

        if request.method == 'POST':
            title = str(data.get('title', '')).strip()
            location = str(data.get('location', '')).strip()
            category = str(data.get('category', 'concert')).strip() or 'concert'
            description = str(data.get('description', '')).strip()
            base_price = float(data.get('base_price', 0) or 0)
            total_capacity = int(data.get('total_capacity', 100) or 100)
            available_quantity = int(data.get('available_quantity', total_capacity) or total_capacity)
            date_value = data.get('date')
            code_type = sanitize_code_type(data.get('code_type', DEFAULT_CODE_TYPE))

            if not title or not location or not date_value:
                db.close()
                return jsonify({"error": "Titre, lieu et date sont requis"}), 400

            try:
                parsed_date = datetime.fromisoformat(str(date_value).replace('Z', '+00:00'))
            except ValueError:
                db.close()
                return jsonify({"error": "Date invalide. Format ISO attendu."}), 400

            event = Event(
                title=title,
                description=description,
                location=location,
                date=parsed_date,
                category=category,
                base_price=base_price,
                total_capacity=max(1, total_capacity),
                available_quantity=max(0, min(available_quantity, total_capacity)),
                is_active=True,
                code_type=code_type,
            )
            db.add(event)
            db.commit()
            db.refresh(event)
            db.close()
            return jsonify({"ok": True, "event": {
                "id": event.id,
                "title": event.title,
                "location": event.location,
                "date": event.date.isoformat(),
                "base_price": float(event.base_price),
                "available_quantity": event.available_quantity,
                "total_capacity": event.total_capacity,
                "code_type": event.code_type,
            }}), 201

        events = db.query(Event).order_by(Event.date.asc()).all()
        payload = [{
            "id": e.id,
            "title": e.title,
            "description": e.description,
            "location": e.location,
            "date": e.date.isoformat() if e.date else None,
            "category": e.category,
            "base_price": float(e.base_price),
            "total_capacity": e.total_capacity,
            "available_quantity": e.available_quantity,
            "is_active": e.is_active,
            "code_type": e.code_type,
        } for e in events]
        db.close()
        return jsonify({"events": payload}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# rest of file continues with the existing validations and scan routes

@app.route('/api/ticket/<ticket_number>', methods=['GET'])
def ticket_details(ticket_number):
    try:
        db = SessionLocal()
        ticket = db.query(Ticket).filter(Ticket.ticket_number == ticket_number).first()
        if not ticket:
            db.close()
            return jsonify({"error": "Billet introuvable"}), 404

        event = db.query(Event).filter(Event.id == ticket.event_id).first()
        code_type = sanitize_code_type(ticket.code_type)

        qr_image = None
        barcode_image = None
        if code_type in ('qr', 'both'):
            qr_image = generate_qr_image(ticket.ticket_number, ticket.barcode_value, ticket.event_id)
        if code_type in ('barcode', 'both'):
            barcode_image = generate_barcode_image(ticket.barcode_value, ticket.ticket_number)

        payload = {
            "ticket_number": ticket.ticket_number,
            "barcode_value": ticket.barcode_value,
            "code_type": code_type,
            "event_title": event.title if event else "N/A",
            "event_date": event.date.isoformat() if event and event.date else None,
            "event_location": event.location if event else "N/A",
            "status": ticket.status,
            "created_at": ticket.timestamp.isoformat() if ticket.timestamp else None,
            "scanned_at": ticket.scanned_at.isoformat() if ticket.scanned_at else None,
            "scanned_by": ticket.scanned_by,
            "scan_location": ticket.scan_location,
            "qr_image": qr_image,
            "barcode_image": barcode_image,
        }
        db.close()
        return jsonify(payload), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ticket/scan', methods=['POST'])
def scan_ticket():
    try:
        data = request.get_json() or {}
        ticket_input = str(data.get('ticket_number', '')).strip() or str(data.get('barcode_value', '')).strip()
        scanned_by = str(data.get('scanned_by', 'system')).strip()
        scan_location = str(data.get('scan_location', 'entrance')).strip()

        if not ticket_input:
            return jsonify({"error": "Numéro de billet ou code-barres requis"}), 400

        db = SessionLocal()
        ticket = db.query(Ticket).filter(or_(Ticket.ticket_number == ticket_input, Ticket.barcode_value == ticket_input)).first()
        if not ticket:
            db.close()
            return jsonify({"error": "Billet introuvable"}), 404

        if ticket.status == 'scanned':
            db.close()
            return jsonify({"ok": False, "error": "Ce billet a déjà été scanné", "scanned_at": ticket.scanned_at.isoformat() if ticket.scanned_at else None, "previous_scan_by": ticket.scanned_by}), 400

        if ticket.status == 'used':
            db.close()
            return jsonify({"ok": False, "error": "Ce billet a déjà été utilisé", "scanned_at": ticket.scanned_at.isoformat() if ticket.scanned_at else None}), 400

        ticket.status = 'scanned'
        ticket.scanned_at = datetime.now()
        ticket.scanned_by = scanned_by
        ticket.scan_location = scan_location

        event = db.query(Event).filter(Event.id == ticket.event_id).first()
        order = db.query(Order).filter(Order.id == ticket.order_id).first()

        db.commit()
        db.close()

        return jsonify({
            "ok": True,
            "ticket_number": ticket.ticket_number,
            "barcode_value": ticket.barcode_value,
            "code_type": ticket.code_type,
            "status": ticket.status,
            "event_title": event.title if event else "N/A",
            "buyer_name": order.payer_name if order else "N/A",
            "scanned_at": ticket.scanned_at.isoformat(),
            "scanned_by": scanned_by,
            "scan_location": scan_location,
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/ticket/scan-history/<ticket_number>', methods=['GET'])
def scan_history(ticket_number):
    try:
        db = SessionLocal()
        ticket = db.query(Ticket).filter(Ticket.ticket_number == ticket_number).first()
        if not ticket:
            db.close()
            return jsonify({"error": "Billet introuvable"}), 404

        payload = {
            "ticket_number": ticket.ticket_number,
            "code_type": ticket.code_type,
            "status": ticket.status,
            "created_at": ticket.timestamp.isoformat() if ticket.timestamp else None,
            "scan_info": {
                "scanned_at": ticket.scanned_at.isoformat() if ticket.scanned_at else None,
                "scanned_by": ticket.scanned_by,
                "scan_location": ticket.scan_location,
            }
        }
        db.close()
        return jsonify(payload), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# Existing legacy routes; kept as-is for compatibility.

@app.route('/validate', methods=['POST'])
def validate():
    try:
        data = request.get_json()
        raw = str(data.get('ticket', ''))
        raw = raw.replace('.', ',')
        numbers = [n.strip() for n in raw.split(',') if n.strip()]
        if not numbers:
            return jsonify({"error": "Aucun numéro de ticket fourni"}), 400

        messages = []
        errors = []
        db = SessionLocal()
        for n in numbers:
            if not n.isdigit():
                errors.append(f"'{n}' invalide")
                continue
            t = int(n)
            ticket = db.query(Ticket).filter_by(ticket_number=str(t)).first()
            if ticket:
                ticket.status = f"validé - {t}"
            else:
                ticket = Ticket(ticket_number=str(t), event_id=1, order_id=1, buyer_id=1, status=f"validé - {t}")
                db.add(ticket)
            messages.append(f"Ticket {t} validé")
        db.commit()
        db.close()

        response = {}
        if messages:
            response["message"] = " | ".join(messages)
        if errors:
            response["error"] = " | ".join(errors)
        return jsonify(response)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/verify')
def verify():
    try:
        raw = request.args.get('ticket', '')
        raw = raw.replace('.', ',')
        numbers = [n.strip() for n in raw.split(',') if n.strip()]
        if not numbers:
            return jsonify({"error": "Aucun numéro de ticket fourni"}), 400

        results = []
        with SessionLocal() as db:
            for n in numbers:
                if not n.isdigit():
                    results.append({"ticket": n, "status": "numéro invalide"})
                    continue
                t = int(n)
                ticket = db.query(Ticket).filter_by(ticket_number=str(t)).first()
                if ticket:
                    results.append({"ticket": t, "status": ticket.status})
                else:
                    results.append({"ticket": t, "status": f"invalide - {t}"})

        return jsonify({"results": results})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/export_word', methods=['POST'])
def export_word():
    try:
        data = request.get_json()
        if not pwd_context.verify(data.get('password', ''), ADMIN_PASSWORD_HASH):
            return jsonify({"error": "Accès refusé"}), 401

        doc = Document()
        doc.add_heading("Tickets Validés", 0)

        db = SessionLocal()
        results = db.query(Ticket).filter(or_(Ticket.status == 'validé', Ticket.status.like('validé%'))).all()
        db.close()

        if not results:
            doc.add_paragraph("Aucun ticket validé.")
        else:
            for ticket in results:
                doc.add_paragraph(f"Ticket {ticket.ticket_number} - Validé le {ticket.timestamp}")

        output = BytesIO()
        doc.save(output)
        output.seek(0)
        return send_file(output, mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document', as_attachment=True, download_name='tickets_valides.docx')
    except Exception as e:
        return jsonify({"error": f"Erreur export: {str(e)}"}), 500


@app.route('/admin', methods=['POST'])
def admin():
    try:
        data = request.get_json()
        if pwd_context.verify(data.get('password', ''), ADMIN_PASSWORD_HASH):
            return jsonify({"success": True})
        return jsonify({"success": False}), 401
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/delete_validated', methods=['POST'])
def delete_validated():
    try:
        data = request.get_json()
        if not pwd_context.verify(data.get('password', ''), ADMIN_PASSWORD_HASH):
            return jsonify({"error": "Accès refusé"}), 401

        ticket_input = data.get("ticket", "")
        db = SessionLocal()

        if not ticket_input:
            deleted = db.query(Ticket).filter(or_(Ticket.status == "validé", Ticket.status.like("validé%"))).delete()
        else:
            raw = str(ticket_input).replace('.', ',')
            numbers = [n.strip() for n in raw.split(',') if n.strip()]
            valid_numbers = [str(int(n)) for n in numbers if n.isdigit()]

            if valid_numbers:
                deleted = db.query(Ticket).filter(and_(Ticket.ticket_number.in_(valid_numbers), or_(Ticket.status == "validé", Ticket.status.like("validé%")))).delete()
            else:
                deleted = 0

        db.commit()
        db.close()
        return jsonify({"message": f"{deleted} ticket(s) supprimé(s)."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/history', methods=['POST', 'GET'])
def history():
    try:
        if request.method == 'POST':
            data = request.get_json()
            if not pwd_context.verify(data.get('password', ''), ADMIN_PASSWORD_HASH):
                return jsonify({"error": "Accès refusé"}), 401

        status = request.args.get("status")
        db = SessionLocal()
        query = db.query(Ticket)

        if status in ("validé", "invalide"):
            query = query.filter(Ticket.status.like(f"{status}%"))

        results = query.order_by(Ticket.timestamp.desc()).limit(MAX_HISTORY_ENTRIES).all()
        db.close()

        return jsonify({"results": [f"Ticket {r.ticket_number} - {r.status} - {r.timestamp}" for r in results]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/ping')
def ping():
    return "pong", 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=FLASK_PORT)

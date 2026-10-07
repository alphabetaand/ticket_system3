import os
import logging
import psycopg2
from flask import Flask, request, jsonify, render_template_string, send_file, make_response, session
from flask_cors import CORS
from passlib.context import CryptContext
from docx import Document
from io import BytesIO
from datetime import datetime
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

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sécurité
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], default="pbkdf2_sha256", pbkdf2_sha256__default_rounds=30000)
ADMIN_PASSWORD_HASH = pwd_context.hash(ADMIN_PASSWORD)

# Créer base de données
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
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False)
    buyer_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    status = Column(String, default='valid')
    qr_hash = Column(String, nullable=True)
    timestamp = Column(DateTime, default=func.now())
    scanned_at = Column(DateTime, nullable=True)

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
            ),
        ])
        db.commit()
    db.close()


init_db()
seed_demo_events()

# =====================
# ETAPE 2 : catalogue d'événements
# =====================

EVENTS_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Événements | TicketHub</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: 'Segoe UI', Arial, sans-serif;
      background: linear-gradient(135deg, #0f172a, #1e293b);
      color: white;
    }
    .container {
      max-width: 1100px;
      margin: 0 auto;
      padding: 30px 20px 60px;
    }
    .topbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 30px;
      border-bottom: 1px solid #334155;
      padding-bottom: 20px;
    }
    .brand {
      font-size: 28px;
      font-weight: bold;
      color: #60a5fa;
    }
    .nav {
      display: flex;
      gap: 15px;
      flex-wrap: wrap;
    }
    .nav a {
      color: #cbd5e1;
      text-decoration: none;
      font-size: 15px;
    }
    h1 {
      margin: 0 0 30px;
      font-size: 34px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 22px;
    }
    .card {
      background: rgba(15, 23, 42, 0.9);
      border: 1px solid #334155;
      border-radius: 18px;
      overflow: hidden;
      box-shadow: 0 8px 20px rgba(0,0,0,0.2);
    }
    .image {
      min-height: 170px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 54px;
      background: linear-gradient(135deg, #3b82f6, #1d4ed8);
    }
    .content {
      padding: 18px;
    }
    .tag {
      display: inline-block;
      background: rgba(96, 165, 250, 0.16);
      color: #bfdbfe;
      border: 1px solid #60a5fa;
      border-radius: 999px;
      font-size: 12px;
      padding: 6px 10px;
      margin-bottom: 12px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    h2 {
      margin: 0 0 10px;
      font-size: 22px;
    }
    .meta {
      color: #cbd5e1;
      font-size: 14px;
      margin-bottom: 10px;
      line-height: 1.6;
    }
    .price {
      color: #4ade80;
      font-size: 30px;
      font-weight: bold;
      margin: 14px 0;
    }
    .availability {
      color: #fbbf24;
      font-weight: 600;
      margin-bottom: 16px;
      font-size: 14px;
    }
    .button {
      width: 100%;
      border: none;
      border-radius: 12px;
      padding: 14px 18px;
      background: #2563eb;
      color: white;
      font-size: 16px;
      font-weight: bold;
      cursor: pointer;
    }
    .button:hover {
      background: #1d4ed8;
    }
    .button:disabled {
      background: #475569;
      cursor: not-allowed;
    }
    .empty {
      text-align: center;
      color: #cbd5e1;
      padding: 40px 20px;
      border: 1px dashed #475569;
      border-radius: 12px;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="topbar">
      <div class="brand">🎫 TicketHub</div>
      <div class="nav">
        <a href="/">Accueil</a>
        <a href="/events">Événements</a>
        <a href="/cart">Panier</a>
        <a href="/admin">Admin</a>
      </div>
    </div>

    <h1>Nos événements</h1>
    <div id="events"></div>
  </div>

  <script>
    async function addToCart(eventId) {
      const res = await fetch('/api/cart/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_id: eventId, quantity: 1 })
      });
      const data = await res.json();
      if (data.ok) {
        window.location.href = '/cart';
      } else {
        alert(data.error || 'Erreur');
      }
    }

    async function loadEvents() {
      const container = document.getElementById('events');
      try {
        const res = await fetch('/api/events');
        const events = await res.json();

        if (!events.length) {
          container.innerHTML = '<div class="empty">Aucun événement disponible pour le moment.</div>';
          return;
        }

        container.innerHTML = '<div class="grid">' + events.map(event => {
          const date = new Date(event.date);
          const dateText = date.toLocaleString('fr-FR', {
            weekday: 'long', day: 'numeric', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit'
          });
          const soldOut = event.available_quantity <= 0;

          return `
            <div class="card">
              <div class="image">🎭</div>
              <div class="content">
                <div class="tag">${event.category || 'événement'}</div>
                <h2>${event.title}</h2>
                <div class="meta">
                  <div>📍 ${event.location}</div>
                  <div>🗓️ ${dateText}</div>
                </div>
                <div class="price">${Number(event.base_price).toLocaleString('fr-FR')} FCFA</div>
                <div class="availability">Places restantes : ${event.available_quantity} / ${event.total_capacity}</div>
                <button class="button" ${soldOut ? 'disabled' : ''} onclick="addToCart(${event.id})">${soldOut ? 'Épuisé' : 'Acheter un billet'}</button>
              </div>
            </div>
          `;
        }).join('') + '</div>';
      } catch (error) {
        container.innerHTML = '<div class="empty">Erreur lors du chargement des événements.</div>';
      }
    }

    loadEvents();
  </script>
</body>
</html>
"""

# =====================
# ETAPE 3 : PANIER AVEC FRAIS DE SERVICE 1%
# =====================

CART_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Panier | TicketHub</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      background: linear-gradient(135deg, #0f172a, #1e293b);
      color: white;
      font-family: 'Segoe UI', Arial, sans-serif;
    }
    .container {
      max-width: 1000px;
      margin: 0 auto;
      padding: 30px 20px 60px;
    }
    .topbar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid #334155;
      padding-bottom: 18px;
      margin-bottom: 30px;
    }
    .brand {
      font-size: 28px;
      font-weight: bold;
      color: #60a5fa;
    }
    .nav a {
      color: #cbd5e1;
      text-decoration: none;
      margin-left: 16px;
    }
    .box {
      background: rgba(15,23,42,0.95);
      border: 1px solid #334155;
      border-radius: 18px;
      padding: 20px;
    }
    .row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      border-bottom: 1px solid #334155;
      padding: 16px 0;
    }
    .row:last-child {
      border-bottom: none;
    }
    .qty {
      display: flex;
      align-items: center;
      gap: 10px;
      margin-top: 8px;
    }
    .qty button {
      width: 32px;
      height: 32px;
      border-radius: 8px;
      border: none;
      background: #475569;
      color: white;
      cursor: pointer;
      font-size: 18px;
    }
    .summary {
      margin-top: 28px;
      background: rgba(15,23,42,0.95);
      border: 1px solid #334155;
      border-radius: 18px;
      padding: 20px;
    }
    .summary-row {
      display: flex;
      justify-content: space-between;
      margin: 12px 0;
      color: #cbd5e1;
    }
    .total {
      font-size: 26px;
      font-weight: bold;
      color: #4ade80;
      margin-top: 20px;
    }
    .button {
      width: 100%;
      margin-top: 20px;
      border: none;
      border-radius: 12px;
      padding: 16px;
      background: #22c55e;
      color: white;
      font-size: 18px;
      font-weight: bold;
      cursor: pointer;
    }
    .button.secondary {
      background: #2563eb;
    }
    .empty {
      text-align: center;
      color: #cbd5e1;
      padding: 40px 20px;
      border: 1px dashed #475569;
      border-radius: 12px;
    }
    .payment-select {
      margin-top: 20px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    select {
      background: #0f172a;
      color: white;
      border: 1px solid #475569;
      border-radius: 10px;
      padding: 12px;
      font-size: 16px;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="topbar">
      <div class="brand">🛒 TicketHub</div>
      <div class="nav">
        <a href="/events">Événements</a>
        <a href="/">Accueil</a>
      </div>
    </div>

    <div id="cart-content"></div>
  </div>

  <script>
    async function loadCart() {
      const container = document.getElementById('cart-content');
      const res = await fetch('/api/cart');
      const data = await res.json();

      if (!data.items || data.items.length === 0) {
        container.innerHTML = `
          <div class="empty">
            <h2>Votre panier est vide</h2>
            <p>Ajoutez des billets pour voir votre commande.</p>
            <a href="/events" style="color:#60a5fa;text-decoration:none;">Voir les événements</a>
          </div>
        `;
        return;
      }

      const rows = data.items.map(item => `
        <div class="box">
          <div class="row">
            <div>
              <h3 style="margin:0 0 8px;">${item.title}</h3>
              <div style="color:#cbd5e1;">${item.location}</div>
              <div class="qty">
                <button onclick="updateQty(${item.event_id}, -1)">-</button>
                <span>${item.quantity}</span>
                <button onclick="updateQty(${item.event_id}, 1)">+</button>
              </div>
            </div>
            <div>
              <div style="font-size:20px;font-weight:bold;color:#4ade80;">${item.total.toLocaleString('fr-FR')} FCFA</div>
              <div style="color:#cbd5e1;margin-top:8px;">${item.unit_price.toLocaleString('fr-FR')} FCFA / billet</div>
            </div>
          </div>
        </div>
      `).join('');

      container.innerHTML = `
        ${rows}
        <div class="summary">
          <div class="summary-row"><span>Sous-total</span><span>${data.subtotal.toLocaleString('fr-FR')} FCFA</span></div>
          <div class="summary-row"><span>Frais de service (1%)</span><span>${data.fee.toLocaleString('fr-FR')} FCFA</span></div>
          <div class="summary-row total"><span>Total</span><span>${data.total.toLocaleString('fr-FR')} FCFA</span></div>
          <div class="payment-select">
            <label for="paymentProvider">Mode de paiement</label>
            <select id="paymentProvider">
              <option value="wave">Wave</option>
              <option value="orange">Orange Money</option>
            </select>
          </div>
          <button class="button secondary" onclick="window.location.href='/events'">Continuer les achats</button>
          <button class="button" onclick="confirmOrder()">Valider la commande</button>
        </div>
      `;
    }

    async function updateQty(eventId, delta) {
      const res = await fetch('/api/cart/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_id: eventId, delta: delta })
      });
      const data = await res.json();
      if (data.ok) {
        loadCart();
      } else {
        alert(data.error || 'Erreur');
      }
    }

    async function confirmOrder() {
      const provider = document.getElementById('paymentProvider')?.value || 'wave';
      const res = await fetch('/api/cart/checkout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ payment_provider: provider })
      });
      const data = await res.json();
      if (data.ok) {
        alert('Commande créée avec succès. Paiement à intégrer ensuite (Wave / Orange Money).');
        window.location.href = '/events';
      } else {
        alert(data.error || 'Erreur de commande');
      }
    }

    loadCart();
  </script>
</body>
</html>
"""

# ==============================================
# Cart session helpers
# ==============================================

def get_cart():
    cart = session.get('cart', {})
    if not isinstance(cart, dict):
        cart = {}
    return cart


def set_cart(cart):
    session['cart'] = cart


def get_cart_items():
    cart = get_cart()
    db = SessionLocal()
    items = []
    subtotal = 0.0
    for event_id_str, qty in cart.items():
        try:
            event_id = int(event_id_str)
        except Exception:
            continue
        event = db.query(Event).filter(Event.id == event_id).first()
        if not event:
            continue
        qty_int = int(qty)
        if qty_int <= 0:
            continue
        unit_price = float(event.base_price)
        total = unit_price * qty_int
        subtotal += total
        items.append({
            'event_id': event.id,
            'title': event.title,
            'location': event.location,
            'unit_price': unit_price,
            'quantity': qty_int,
            'total': total,
        })
    db.close()
    fee = round(subtotal * SERVICE_FEE_RATE, 2)
    total = round(subtotal + fee, 2)
    return items, subtotal, fee, total


# ==============================================
# Routes
# ==============================================

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'tickethub-secret-key-change-me')
CORS(app)

@app.after_request
def add_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/')
def home():
    response = make_response(render_template_string(MOBILE_TEMPLATE))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/events')
def events_page():
    response = make_response(render_template_string(EVENTS_TEMPLATE))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/cart')
def cart_page():
    response = make_response(render_template_string(CART_TEMPLATE))
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

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
        } for e in events]
        return jsonify(payload), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/cart/add', methods=['POST'])
def cart_add():
    try:
        data = request.get_json() or {}
        event_id = int(data.get('event_id'))
        qty = int(data.get('quantity', 1))
        if qty <= 0:
            return jsonify({"error": "Quantité invalide"}), 400

        db = SessionLocal()
        event = db.query(Event).filter(Event.id == event_id).first()
        db.close()
        if not event:
            return jsonify({"error": "Événement introuvable"}), 404
        if event.available_quantity <= 0:
            return jsonify({"error": "Plus de billets disponibles"}), 400

        cart = get_cart()
        current = int(cart.get(str(event_id), 0))
        cart[str(event_id)] = min(current + qty, event.available_quantity)
        set_cart(cart)
        return jsonify({"ok": True, "cart": cart}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/cart/update', methods=['POST'])
def cart_update():
    try:
        data = request.get_json() or {}
        event_id = int(data.get('event_id'))
        delta = int(data.get('delta', 0))
        cart = get_cart()
        current = int(cart.get(str(event_id), 0))
        new_qty = current + delta
        if new_qty <= 0:
            cart.pop(str(event_id), None)
        else:
            cart[str(event_id)] = new_qty
        set_cart(cart)
        return jsonify({"ok": True, "cart": cart}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/cart', methods=['GET'])
def cart_view():
    try:
        items, subtotal, fee, total = get_cart_items()
        return jsonify({
            "items": items,
            "subtotal": round(subtotal, 2),
            "fee": round(fee, 2),
            "total": round(total, 2)
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
        provider_valid = payment_provider in ('wave', 'orange')
        if not provider_valid:
            return jsonify({"error": "Opérateur de paiement invalide"}), 400

        db = SessionLocal()
        order_number = f"ORD-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        order = Order(
            order_number=order_number,
            user_id=1,
            total_amount=round(total, 2),
            fee_amount=round(fee, 2),
            status='pending',
            payment_method='mobile_money',
            payment_provider=payment_provider,
        )
        db.add(order)
        db.flush()

        for item in items:
            db.add(OrderItem(
                order_id=order.id,
                event_id=item['event_id'],
                quantity=item['quantity'],
                unit_price=item['unit_price'],
                total_price=item['total'],
            ))

            event = db.query(Event).filter(Event.id == item['event_id']).first()
            if event:
                event.available_quantity = max(0, event.available_quantity - item['quantity'])

        db.commit()
        db.close()

        session['cart'] = {}
        return jsonify({
            "ok": True,
            "order_number": order_number,
            "payment_provider": payment_provider,
            "total": round(total, 2),
            "fee": round(fee, 2)
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

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
            ticket = db.query(Ticket).filter(Ticket.ticket_number == str(t)).first()
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
                ticket = db.query(Ticket).filter(Ticket.ticket_number == str(t)).first()
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
        results = db.query(Ticket).filter(
            or_(
                Ticket.status == 'validé',
                Ticket.status.like('validé%')
            )
        ).all()
        db.close()

        if not results:
            doc.add_paragraph("Aucun ticket validé.")
        else:
            for ticket in results:
                doc.add_paragraph(f"Ticket {ticket.ticket_number} - Validé le {ticket.timestamp}")

        output = BytesIO()
        doc.save(output)
        output.seek(0)
        return send_file(
            output,
            mimetype='application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            as_attachment=True,
            download_name='tickets_valides.docx'
        )
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
            deleted = db.query(Ticket).filter(
                or_(
                    Ticket.status == "validé",
                    Ticket.status.like("validé%")
                )
            ).delete()
        else:
            raw = str(ticket_input).replace('.', ',')
            numbers = [n.strip() for n in raw.split(',') if n.strip()]
            valid_numbers = [str(int(n)) for n in numbers if n.isdigit()]

            if valid_numbers:
                deleted = db.query(Ticket).filter(
                    and_(
                        Ticket.ticket_number.in_(valid_numbers),
                        or_(
                            Ticket.status == "validé",
                            Ticket.status.like("validé%")
                        )
                    )
                ).delete()
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

        return jsonify({
            "results": [
                f"Ticket {r.ticket_number} - {r.status} - {r.timestamp}" for r in results
            ]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/ping')
def ping():
    return "pong", 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=FLASK_PORT)

import os 
import logging
import psycopg2
from flask import Flask, request, jsonify, render_template_string, send_file
from flask_cors import CORS
from passlib.context import CryptContext
from docx import Document
from io import BytesIO
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, DateTime, func
from sqlalchemy.orm import declarative_base, sessionmaker
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

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Sécurité
pwd_context = CryptContext(schemes=["pbkdf2_sha256"], default="pbkdf2_sha256", pbkdf2_sha256__default_rounds=30000)
ADMIN_PASSWORD_HASH = pwd_context.hash(ADMIN_PASSWORD)

# Créer base de données
os.makedirs(QR_FOLDER, exist_ok=True)

class Ticket(Base):
    __tablename__ = "tickets"
    ticket_number = Column(Integer, primary_key=True, index=True)
    status = Column(String, default='invalide')
    qr_hash = Column(String, unique=True, nullable=True)
    timestamp = Column(DateTime, default=func.now())

def init_db():
    Base.metadata.create_all(bind=engine)

init_db()

# Interface mobile HTML
with open("static/icon.png", "rb") as f: pass  # vérifie que l'icône existe
MOBILE_TEMPLATE = """
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"/>
  <title>Saint Anne Show</title>
  <link rel="icon" href="/static/icon.png" type="image/png">
  <link rel="apple-touch-icon" href="/static/icon.png">
  <meta name="theme-color" content="#0f172a">
  <meta name="mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
  <style>
    * { box-sizing: border-box; }
    html, body {
      margin: 0;
      padding: 0;
      height: 100%;
      width: 100%;
      font-family: 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(to bottom right, #0f172a, #1e293b);
      color: white;
      overflow-x: hidden;
    }
    .page {
      display: none;
      flex-direction: column;
      align-items: center;
      justify-content: flex-start;
      min-height: 100vh;
      padding: 30px 20px 100px;
    }
    .page.active { display: flex; }

    .logo img {
      width: 220px;
      margin-bottom: 30px;
    }

    input, select, textarea {
      padding: 16px;
      margin: 12px 0;
      border: none;
      border-radius: 12px;
      font-size: 16px;
      width: 100%;
      max-width: 360px;
      font-family: 'Segoe UI', Roboto, sans-serif;
    }

    textarea {
      min-height: 120px;
      resize: vertical;
      color: #0f172a;
    }

    button {
      padding: 16px;
      margin-bottom: 16px;
      font-size: 17px;
      font-weight: bold;
      border: none;
      border-radius: 12px;
      cursor: pointer;
      width: 100%;
      max-width: 360px;
      color: white;
    }

    .validate { background-color: #22c55e; }
    .validate-bulk { background-color: #16a34a; }
    .verify   { background-color: #3b82f6; }
    .verify-bulk { background-color: #1d4ed8; }
    .history  { background-color: #f97316; }
    .export   { background-color: #facc15; color: black; }
    .delete   { background-color: #ef4444; }

    .nav-links {
      text-align: center;
      margin-top: 20px;
    }
    .nav-links button {
      background: none;
      border: none;
      color: #a5b4fc;
      font-size: 15px;
      margin: 0 8px;
      text-decoration: underline;
      cursor: pointer;
    }

    #result-validation, #result-verification, #result-bulk-validation, #result-bulk-verification {
      margin-top: 20px;
      font-size: 16px;
      font-weight: bold;
      color: inherit;
      padding: 12px;
      border-radius: 8px;
      max-width: 360px;
      text-align: center;
    }

    .result-details {
      margin-top: 15px;
      font-size: 14px;
      max-width: 360px;
      padding: 12px;
      background: rgba(255,255,255,0.1);
      border-radius: 8px;
    }
  </style>
</head>
<body>

  <!-- Page Validation -->
  <div class="page active" id="validation">
    <div class="logo"><img src="/static/logo.png" alt="Sainte Anne Show"></div>
    <input type="number" id="ticketInput" placeholder="Numéro de ticket">
    <button class="validate" onclick="validateTicket()">✅ Valider</button>
    <div id="result-validation"></div>
    <div class="nav-links">
      <button onclick="showPage('bulk-validation')">📦 Valider en masse</button>
      <button onclick="showPage('verification')">🔍 Vérifier</button>
      <button onclick="showPage('admin')">🛠️ Admin</button>
    </div>
  </div>

  <!-- Page Validation en Masse -->
  <div class="page" id="bulk-validation">
    <div class="logo"><img src="/static/logo.png" alt="Sainte Anne Show"></div>
    <textarea id="bulkTicketsValidate" placeholder="Entrez les numéros de ticket (séparés par des virgules ou des retours à la ligne)&#10;Exemple: 1, 2, 3&#10;ou&#10;1&#10;2&#10;3"></textarea>
    <button class="validate-bulk" onclick="validateTicketsBulk()">📦 Valider en masse</button>
    <div id="result-bulk-validation"></div>
    <div class="nav-links">
      <button onclick="showPage('validation')">✅ Valider un</button>
      <button onclick="showPage('bulk-verification')">🔍 Vérifier en masse</button>
      <button onclick="showPage('admin')">🛠️ Admin</button>
    </div>
  </div>

  <!-- Page Vérification -->
  <div class="page" id="verification">
    <div class="logo"><img src="/static/logo.png" alt="Sainte Anne Show"></div>
    <input type="number" id="ticketInputVerify" placeholder="Numéro de ticket">
    <button class="verify" onclick="verifyTicket()">🔍 Vérifier</button>
    <div id="result-verification"></div>
    <div class="nav-links">
      <button onclick="showPage('validation')">✅ Valider</button>
      <button onclick="showPage('bulk-verification')">📦 Vérifier en masse</button>
      <button onclick="showPage('admin')">🛠️ Admin</button>
    </div>
  </div>

  <!-- Page Vérification en Masse -->
  <div class="page" id="bulk-verification">
    <div class="logo"><img src="/static/logo.png" alt="Sainte Anne Show"></div>
    <textarea id="bulkTicketsVerify" placeholder="Entrez les numéros de ticket (séparés par des virgules ou des retours à la ligne)&#10;Exemple: 1, 2, 3&#10;ou&#10;1&#10;2&#10;3"></textarea>
    <button class="verify-bulk" onclick="verifyTicketsBulk()">📦 Vérifier en masse</button>
    <div id="result-bulk-verification"></div>
    <div class="nav-links">
      <button onclick="showPage('verification')">🔍 Vérifier un</button>
      <button onclick="showPage('bulk-validation')">📦 Valider en masse</button>
      <button onclick="showPage('admin')">🛠️ Admin</button>
    </div>
  </div>

  <!-- Page Admin -->
  <div class="page" id="admin">
    <div class="logo"><img src="/static/logo.png" alt="Sainte Anne Show"></div>
    <input type="password" id="adminPass" placeholder="Mot de passe admin">
    <select id="statusFilter" onchange="loadHistory()">
      <option value="">Tous les statuts</option>
      <option value="validé">Validé</option>
      <option value="invalide">Invalide</option>
    </select>
    <button class="history" onclick="loadHistory()">📄 Historique</button>
    <button class="export" onclick="exportData()">📤 Exporter (.docx)</button>
    <input type="number" id="deleteTicket" placeholder="Ticket à supprimer (vide = tous)">
    <button class="delete" onclick="deleteValidated()">🗑️ Supprimer</button>
    <div class="nav-links">
      <button onclick="showPage('validation')">✅ Valider</button>
      <button onclick="showPage('verification')">🔍 Vérifier</button>
    </div>
    <div id="result"></div>
    <div id="historyList"></div>
  </div>

 <script>
  function showPage(id) {
    document.querySelectorAll(".page").forEach(p => p.classList.remove("active"));
    document.getElementById(id).classList.add("active");
  }

  const apiBase = window.location.origin;

  async function validateTicket() {
    const t = document.getElementById('ticketInput').value;
    if (!t) return alert("Veuillez entrer un numéro de ticket.");
    const r = await fetch(`${apiBase}/validate`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ticket: t})
    });
    const d = await r.json();
    const result = document.getElementById('result-validation');
    result.innerText = d.message || d.error;
    result.style.color = d.message ? "#22c55e" : "red";
  }

  async function validateTicketsBulk() {
    const textarea = document.getElementById('bulkTicketsValidate').value;
    if (!textarea.trim()) return alert("Veuillez entrer au moins un numéro de ticket.");
    
    const tickets = textarea
      .split(/[,\n]/)
      .map(t => t.trim())
      .filter(t => t && !isNaN(t))
      .map(t => parseInt(t));
    
    if (tickets.length === 0) return alert("Aucun numéro de ticket valide trouvé.");
    
    const r = await fetch(`${apiBase}/validate_bulk`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({tickets: tickets})
    });
    const d = await r.json();
    const result = document.getElementById('result-bulk-validation');
    
    if (d.message) {
      result.innerHTML = `
        <div style="background-color: rgba(34, 197, 94, 0.2); padding: 12px; border-radius: 8px;">
          <strong>✅ ${d.message}</strong>
          <div class="result-details">
            <div>✔️ Validés: ${d.success || 0}</div>
            <div>⚠️ Échoués: ${d.failed || 0}</div>
            <div>📊 Total traité: ${d.total || 0}</div>
          </div>
        </div>
      `;
      result.style.color = "#22c55e";
      document.getElementById('bulkTicketsValidate').value = '';
    } else {
      result.innerText = d.error || "Erreur inconnue";
      result.style.color = "red";
    }
  }

  async function verifyTicket() {
    const t = document.getElementById('ticketInputVerify').value;
    if (!t) return alert("Veuillez entrer un numéro de ticket.");
    const r = await fetch(`${apiBase}/verify?ticket=${t}`);
    const d = await r.json();
    const result = document.getElementById('result-verification');

    if (d.status) {
      result.innerText = d.status;
      if (d.status.includes("validé")) {
        result.style.color = "#22c55e";
      } else if (d.status.includes("invalide")) {
        result.style.color = "#ef4444";
      } else {
        result.style.color = "#facc15";
      }
    } else {
      result.innerText = d.error || "Erreur inconnue";
      result.style.color = "red";
    }
  }

  async function verifyTicketsBulk() {
    const textarea = document.getElementById('bulkTicketsVerify').value;
    if (!textarea.trim()) return alert("Veuillez entrer au moins un numéro de ticket.");
    
    const tickets = textarea
      .split(/[,\n]/)
      .map(t => t.trim())
      .filter(t => t && !isNaN(t))
      .map(t => parseInt(t));
    
    if (tickets.length === 0) return alert("Aucun numéro de ticket valide trouvé.");
    
    const r = await fetch(`${apiBase}/verify_bulk`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({tickets: tickets})
    });
    const d = await r.json();
    const result = document.getElementById('result-bulk-verification');
    
    if (d.results) {
      let html = `
        <div style="background-color: rgba(59, 130, 246, 0.2); padding: 12px; border-radius: 8px;">
          <strong>🔍 Résultats de vérification</strong>
          <div class="result-details">
            <div>✔️ Validés: ${d.validated || 0}</div>
            <div>❌ Invalides: ${d.invalid || 0}</div>
            <div>📊 Total vérifié: ${d.total || 0}</div>
      `;
      
      if (d.details && d.details.length > 0) {
        html += '<div style="margin-top: 10px; max-height: 200px; overflow-y: auto; font-size: 12px;">';
        d.details.forEach(detail => {
          const color = detail.status.includes('validé') ? '#22c55e' : '#ef4444';
          html += `<div style="color: ${color}; margin: 5px 0;">Ticket ${detail.ticket}: ${detail.status}</div>`;
        });
        html += '</div>';
      }
      
      html += '</div></div>';
      result.innerHTML = html;
      result.style.color = "#3b82f6";
      document.getElementById('bulkTicketsVerify').value = '';
    } else {
      result.innerText = d.error || "Erreur inconnue";
      result.style.color = "red";
    }
  }

  async function exportData() {
    const r = await fetch(`${apiBase}/export_word`);
    const blob = await r.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'tickets.docx';
    a.click();
  }

  async function loadHistory() {
    const status = document.getElementById('statusFilter').value;
    const r = await fetch(`${apiBase}/history?status=${status}`);
    const div = document.getElementById('historyList');
    try {
      const list = await r.json();
      if (Array.isArray(list) && list.length > 0) {
        div.innerHTML = list.map(e => `<div>🕒 ${e}</div>`).join('');
      } else if (Array.isArray(list)) {
        div.innerHTML = "<em>Aucun ticket à afficher.</em>";
      } else if (list.error) {
        div.innerHTML = `<span style='color:red'>Erreur : ${list.error}</span>`;
      }
    } catch (err) {
      div.innerHTML = "<span style='color:red'>Erreur de chargement de l'historique.</span>";
    }
  }

  async function deleteValidated() {
    const pwd = document.getElementById('adminPass').value;
    const ticket = document.getElementById('deleteTicket').value;
    const confirmDelete = confirm(ticket ? `Supprimer le ticket validé N°${ticket} ?` : "Confirmer la suppression de tous les tickets validés ?");
    if (!confirmDelete) return;

    const r = await fetch(`${apiBase}/delete_validated`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({password: pwd, ticket: ticket || null})
    });
    const d = await r.json();
    document.getElementById('result').innerText = d.message || d.error;
  }
</script>
</body>
</html>
"""
# Flask App
app = Flask(__name__)
CORS(app)

@app.after_request
def add_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    return response

@app.route('/')
def home():
    return render_template_string(MOBILE_TEMPLATE)

@app.route('/validate', methods=['POST'])
def validate():
    try:
        data = request.get_json()
        t = int(data.get('ticket'))
        db = SessionLocal()
        ticket = db.query(Ticket).filter_by(ticket_number=t).first()
        if ticket:
           ticket.status = f"validé - {t}"
        else:
          ticket = Ticket(ticket_number=t, status=f"validé - {t}")
        db.add(ticket)
        db.commit()
        db.close()
        return jsonify({"message": f"Ticket {t} validé"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/validate_bulk', methods=['POST'])
def validate_bulk():
    try:
        data = request.get_json()
        tickets = data.get('tickets', [])
        
        if not isinstance(tickets, list) or len(tickets) == 0:
            return jsonify({"error": "Aucun ticket fourni"}), 400
        
        db = SessionLocal()
        success_count = 0
        failed_count = 0
        
        for ticket_num in tickets:
            try:
                t = int(ticket_num)
                ticket = db.query(Ticket).filter_by(ticket_number=t).first()
                if ticket:
                    ticket.status = f"validé - {t}"
                else:
                    ticket = Ticket(ticket_number=t, status=f"validé - {t}")
                db.add(ticket)
                success_count += 1
            except:
                failed_count += 1
        
        db.commit()
        db.close()
        
        return jsonify({
            "message": f"{success_count} ticket(s) validé(s) avec succès",
            "success": success_count,
            "failed": failed_count,
            "total": len(tickets)
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/verify')
def verify():
    try:
        t = request.args.get('ticket')
        with SessionLocal() as db:
            ticket = db.query(Ticket).filter_by(ticket_number=t).first()

            if ticket:
                result_status = ticket.status
            else:
                ticket = Ticket(ticket_number=int(t), status=f"invalide - {t}")
                db.add(ticket)
                db.commit()
                result_status = ticket.status

        return jsonify({"ticket": t, "status": result_status})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/verify_bulk', methods=['POST'])
def verify_bulk():
    try:
        data = request.get_json()
        tickets = data.get('tickets', [])
        
        if not isinstance(tickets, list) or len(tickets) == 0:
            return jsonify({"error": "Aucun ticket fourni"}), 400
        
        db = SessionLocal()
        validated_count = 0
        invalid_count = 0
        details = []
        
        for ticket_num in tickets:
            try:
                t = int(ticket_num)
                ticket = db.query(Ticket).filter_by(ticket_number=t).first()
                
                if ticket:
                    result_status = ticket.status
                    if "validé" in result_status:
                        validated_count += 1
                    else:
                        invalid_count += 1
                else:
                    ticket = Ticket(ticket_number=t, status=f"invalide - {t}")
                    db.add(ticket)
                    result_status = ticket.status
                    invalid_count += 1
                
                details.append({
                    "ticket": t,
                    "status": result_status
                })
            except:
                invalid_count += 1
                details.append({
                    "ticket": ticket_num,
                    "status": "erreur - numéro invalide"
                })
        
        db.commit()
        db.close()
        
        return jsonify({
            "results": True,
            "validated": validated_count,
            "invalid": invalid_count,
            "total": len(tickets),
            "details": details[:10]  # Limiter à 10 détails pour l'affichage
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/export_word')
def export_word():
    try:
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

        ticket = data.get("ticket")
        db = SessionLocal()
        if ticket and str(ticket).isdigit():
              deleted = db.query(Ticket).filter(
             and_(
              Ticket.ticket_number == int(ticket),
               or_(
                 Ticket.status == "validé",
                 Ticket.status.like("validé%")
               )
           )
         ).delete()
        else:
           deleted = db.query(Ticket).filter(
        or_(
            Ticket.status == "validé",
            Ticket.status.like("validé%")
        )
       ).delete()
                                        
        db.commit()
        db.close()
        return jsonify({"message": f"{deleted} ticket(s) supprimé(s)."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/history')
def history():
    try:
        status = request.args.get("status")
        db = SessionLocal()
        query = db.query(Ticket)

        if status in ("validé", "invalide"):
            query = query.filter(Ticket.status.like(f"{status}%"))

        results = query.order_by(Ticket.timestamp.desc()).limit(MAX_HISTORY_ENTRIES).all()
        db.close()

        return jsonify([
            f"Ticket {r.ticket_number} - {r.status} - {r.timestamp}" for r in results
        ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/ping')
def ping():
    return "pong", 200
if __name__ == '__main__':
 app.run(host='0.0.0.0', port=FLASK_PORT)

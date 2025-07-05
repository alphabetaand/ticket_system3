# version Flask avec mot de passe modifié, nom mis à jour et icône intégrée
import sqlite3
import os
import logging
from flask import Flask, request, jsonify, render_template_string, send_file
from flask_cors import CORS
from passlib.context import CryptContext
from docx import Document
from io import BytesIO
from datetime import datetime

# Configuration
QR_FOLDER = "qrcodes/"
DB_PATH = "tickets.db"
ADMIN_PASSWORD = "alphonse2000"  # nouveau mot de passe admin
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
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''CREATE TABLE IF NOT EXISTS tickets (
                            ticket_number INTEGER PRIMARY KEY,
                            status TEXT DEFAULT 'invalide',
                            qr_hash TEXT UNIQUE,
                            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP)''')
        conn.commit()
        logger.info("Base de données initialisée")

init_db()

# Interface mobile HTML
with open("static/icon.png", "rb") as f: pass  # vérifie que l'icône existe

MOBILE_TEMPLATE = """
<!DOCTYPE html>
<html lang=\"fr\">
<head>
  <meta charset=\"UTF-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
  <title>Saint Anne Show</title>
  <link rel=\"icon\" type=\"image/png\" href=\"/static/icon.png\">
  <link rel=\"apple-touch-icon\" href=\"/static/icon.png\">
  <meta name=\"theme-color\" content=\"#1e3a8a\">
  <meta name=\"apple-mobile-web-app-capable\" content=\"yes\">
  <meta name=\"apple-mobile-web-app-title\" content=\"Saint Anne Show\">
  <style>
    body { font-family: 'Segoe UI', sans-serif; background: linear-gradient(to right, #fceabb, #f8b500); display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; }
    .container { background-color: white; padding: 30px; border-radius: 15px; box-shadow: 0 8px 16px rgba(0, 0, 0, 0.25); text-align: center; width: 90%; max-width: 400px; }
    h2 { color: #f57c00; margin-bottom: 20px; }
    input[type=number], input[type=password], select { width: 100%; padding: 12px; margin-bottom: 15px; border: 1px solid #ccc; border-radius: 8px; font-size: 16px; }
    button { width: 100%; padding: 12px; margin-bottom: 10px; font-size: 16px; border: none; border-radius: 8px; cursor: pointer; transition: background-color 0.3s; }
    button.validate { background-color: #4caf50; color: white; }
    button.verify { background-color: #2196f3; color: white; }
    button.export { background-color: #ff9800; color: white; }
    button.admin { background-color: #e91e63; color: white; }
    button.history { background-color: #9c27b0; color: white; }
    button.delete { background-color: #f44336; color: white; }
    button:hover { opacity: 0.9; }
    #result { margin-top: 15px; font-weight: bold; color: #333; }
    #historyList { margin-top: 15px; text-align: left; font-size: 14px; max-height: 150px; overflow-y: auto; }
  </style>
</head>
<body>
  <div class=\"container\">
    <h2>🎟️ SAINT ANNE SHOW</h2>
    <input type=\"number\" id=\"ticketInput\" placeholder=\"Numéro de ticket\"><br>
    <button class=\"validate\" onclick=\"validateTicket()\">Valider</button>
    <button class=\"verify\" onclick=\"verifyTicket()\">Vérifier</button>
    <button class=\"export\" onclick=\"exportData()\">Exporter</button>
    <select id=\"statusFilter\" onchange=\"loadHistory()\">
      <option value=\"\">Tous les statuts</option>
      <option value=\"validé\">Validé</option>
      <option value=\"invalide\">Invalide</option>
    </select>
    <button class=\"history\" onclick=\"loadHistory()\">Voir Historique</button>
    <input type=\"password\" id=\"adminPass\" placeholder=\"Mot de passe admin\">
    <input type=\"number\" id=\"deleteTicket\" placeholder=\"Ticket à supprimer (laisser vide pour tous)\">
    <button class=\"delete\" onclick=\"deleteValidated()\">Supprimer</button>
    <div id=\"result\"></div>
    <div id=\"historyList\"></div>
  </div>
  <script>
    const apiBase = window.location.origin;

    async function validateTicket() {
      const t = document.getElementById('ticketInput').value;
      if (!t) return alert("Veuillez entrer un numéro de ticket.");
      const r = await fetch(`${apiBase}/validate`, {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ticket: t}) });
      const d = await r.json();
      document.getElementById('result').innerText = d.message || d.error;
    }

    async function verifyTicket() {
      const t = document.getElementById('ticketInput').value;
      if (!t) return alert("Veuillez entrer un numéro de ticket.");
      const r = await fetch(`${apiBase}/verify?ticket=${t}`);
      const d = await r.json();
      document.getElementById('result').innerText = d.status || d.error;
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
        t = data.get('ticket')
        if not t or not str(t).isdigit():
            return jsonify({"error": "Numéro invalide"}), 400
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("INSERT INTO tickets (ticket_number, status) VALUES (?, 'validé') ON CONFLICT(ticket_number) DO UPDATE SET status='validé'", (t,))
            conn.commit()
        return jsonify({"message": f"Ticket {t} validé"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/verify')
def verify():
    try:
        t = request.args.get('ticket')
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT status FROM tickets WHERE ticket_number=?", (t,))
            row = cursor.fetchone()
            return jsonify({"ticket": t, "status": row[0] if row else 'invalide'})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/export_word')
def export_word():
    try:
        doc = Document()
        doc.add_heading("Tickets Validés", 0)

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            # On sélectionne uniquement les colonnes existantes
            cursor.execute("SELECT ticket_number, timestamp FROM tickets WHERE status='validé'")
            results = cursor.fetchall()

            if not results:
                doc.add_paragraph("Aucun ticket validé.")
            else:
                for ticket_number, timestamp in results:
                    doc.add_paragraph(f"Ticket {ticket_number} - Validé le {timestamp}")

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
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            if ticket and str(ticket).isdigit():
                cursor.execute("DELETE FROM tickets WHERE ticket_number=? AND status='validé'", (ticket,))
            else:
                cursor.execute("DELETE FROM tickets WHERE status='validé'")
            deleted = cursor.rowcount
            conn.commit()
        return jsonify({"message": f"{deleted} ticket(s) supprimé(s)."})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/history')
def history():
    try:
        status = request.args.get("status")
        query = "SELECT ticket_number, status, timestamp FROM tickets"
        params = []
        if status in ("validé", "invalide"):
            query += " WHERE status=?"
            params.append(status)
        query += " ORDER BY timestamp DESC LIMIT ?"
        params.append(MAX_HISTORY_ENTRIES)

        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            results = cursor.fetchall()
            return jsonify([
                f"Ticket {r[0]} - {r[1]} - {r[2]}" for r in results
            ])
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/ping')
def ping():
    return "pong", 200

#if __name__ == '__main__':
#   app.run(host='0.0.0.0', port=FLASK_PORT)

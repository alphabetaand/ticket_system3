# Démarrage local avec VS Code

## Prérequis

- Python 3.10 ou plus récent
- VS Code et l'extension **Python** de Microsoft

## Installation

Ouvrir le dossier du dépôt dans VS Code, puis dans le terminal intégré :

```bash
python -m venv .venv
```

Activer l'environnement virtuel :

- Windows PowerShell : `.venv\\Scripts\\Activate.ps1`
- macOS/Linux : `source .venv/bin/activate`

Installer les dépendances :

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

L'application utilise SQLite par défaut (`ticket_system.db`) et crée la base ainsi que les événements de démonstration au premier lancement. La configuration VS Code force SQLite pour le profil local et ne nécessite donc pas de base PostgreSQL distante.

## Lancer le serveur

Dans VS Code, ouvrir **Run and Debug** (Ctrl+Shift+D / Cmd+Shift+D), choisir **Ticket System (local)** et démarrer. Sinon, dans le terminal :

```bash
python ticket_system_unified.py
```

Ouvrir http://127.0.0.1:5000/health pour contrôler le serveur et http://127.0.0.1:5000/api/events pour voir les événements. Arrêter avec Ctrl+C.

## Test rapide

```bash
python -m unittest discover -s tests -v
```

Le test de fumée vérifie l'import de l'application et ses routes de santé/catalogue avec une base SQLite temporaire. Cette configuration est réservée au développement local : ne réutilisez pas la clé secrète de VS Code ni les identifiants de démonstration en production.

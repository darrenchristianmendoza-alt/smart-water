"""
smart_water/
├── app.py                  ← Run this to start the system
├── config.py               ← All settings
├── database/
│   ├── __init__.py
│   └── db.py               ← SQLite connection + schema
├── collector/
│   ├── __init__.py
│   └── generator.py        ← Random data generator (simulates Peacefair meter)
├── api/
│   ├── __init__.py
│   └── routes.py           ← All Flask API endpoints
├── templates/
│   └── index.html          ← Dashboard UI
└── static/
    ├── css/
    │   └── style.css
    └── js/
        └── dashboard.js

Run:
    cd smart_water
    python app.py

Then open: http://localhost:5000
"""

from flask import Flask
from api.routes import api_bp
from database.db import init_db
from collector.generator import DataGenerator

def create_app():
    app = Flask(__name__)
    app.register_blueprint(api_bp)
    return app

if __name__ == "__main__":
    # 1. Initialize database + tables
    init_db()

    # 2. Seed 7 days of historical data (only on first run)
    from database.db import seed_historical_data
    seed_historical_data()

    # 3. Start background data collector
    gen = DataGenerator()
    gen.start()

    # 4. Launch Flask
    app = create_app()
    print("\n" + "=" * 55)
    print("  Smart Water System — Data Collection Dashboard")
    print("  http://localhost:5000")
    print("=" * 55 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)
from flask import Flask
from api.routes import api_bp
from database.db import init_db, seed_historical_data
from collector.generator import DataGenerator

_generator = None

def create_app():
    global _generator

    app = Flask(__name__)
    app.register_blueprint(api_bp)
    return app

# This runs at module import time — guaranteed to execute
print("[STARTUP] Initializing...")
init_db()
seed_historical_data()

if _generator is None:
    _generator = DataGenerator()
    _generator.start()

print("[STARTUP] Done — app ready")

app = create_app()

if __name__ == "__main__":
    print("\n" + "=" * 55)
    print("  Smart Water System — Data Collection Dashboard")
    print("  http://localhost:5000")
    print("=" * 55 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)

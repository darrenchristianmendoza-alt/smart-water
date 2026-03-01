# config.py — All system settings in one place

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = os.environ.get("DB_PATH", os.path.join(BASE_DIR, "database", "smart_water.db"))

# ── Data Collection ───────────────────────────────────────────────────────────
COLLECT_INTERVAL_SEC = 1

# ── Peacefair Meter Simulation Ranges ─────────────────────────────────────────
NOMINAL_VOLTAGE      = 218.0
VOLTAGE_STD          = 1.5
VOLTAGE_MIN          = 210.0
VOLTAGE_MAX          = 230.0

CURRENT_RUNNING_MIN  = 3.2
CURRENT_RUNNING_MAX  = 4.4
CURRENT_IDLE_MIN     = 0.01
CURRENT_IDLE_MAX     = 0.08

# ── Pump Cycle (seconds) ──────────────────────────────────────────────────────
PUMP_ON_DURATION     = 35
PUMP_OFF_DURATION    = 10
PUMP_CYCLE           = PUMP_ON_DURATION + PUMP_OFF_DURATION

# ── Detection Thresholds ──────────────────────────────────────────────────────
PUMP_ON_CURRENT       = 0.5
FAULT_CURRENT         = 4.6
POWER_CUT_VOLTAGE     = 50.0
GRID_RESTORED_VOLTAGE = 200.0

# ── Battery Backup ────────────────────────────────────────────────────────────
BATTERY_VOLTAGE      = 12.0
BATTERY_CURRENT_MIN  = 3.4
BATTERY_CURRENT_MAX  = 3.9
BATTERY_CAPACITY_AH  = 100
BATTERY_DOD          = 0.8

# ── Outage Simulation ─────────────────────────────────────────────────────────
OUTAGE_MIN_INTERVAL  = 45
OUTAGE_MAX_INTERVAL  = 120
OUTAGE_MIN_DURATION  = 8
OUTAGE_MAX_DURATION  = 20
FAULT_PROBABILITY    = 0.005

# ── Historical Seed Data ──────────────────────────────────────────────────────
SEED_DAYS            = 7
SEED_SAMPLE_EVERY    = 10
SEED_START_ENERGY    = 9.33

# ── Flask ─────────────────────────────────────────────────────────────────────
FLASK_HOST           = "0.0.0.0"
FLASK_PORT           = 5000
FLASK_DEBUG          = False

# ══════════════════════════════════════════════════════════════════════════════
#  LLM / OLLAMA SETTINGS
#  Paste your ngrok Public URL from Google Colab here
#  e.g.  "https://abc123.ngrok-free.app"
# ══════════════════════════════════════════════════════════════════════════════
OLLAMA_URL     = os.environ.get("OLLAMA_URL", "https://bristol-papyral-rippingly.ngrok-free.dev")
OLLAMA_MODEL   = os.environ.get("OLLAMA_MODEL", "mistral")
OLLAMA_TIMEOUT = 60      # seconds — Mistral can be slow on first response
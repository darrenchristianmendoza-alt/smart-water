# database/db.py — SQLite schema, connection helper, seed data

import os
import random
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

# ── Connection ────────────────────────────────────────────────────────────────

@contextmanager
def get_db():
    """Context manager — auto-commits and closes the connection."""
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row          # rows behave like dicts
    conn.execute("PRAGMA journal_mode=WAL") # allow concurrent reads during writes
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Schema ────────────────────────────────────────────────────────────────────

SCHEMA = """
-- Per-second sensor readings (core table)
CREATE TABLE IF NOT EXISTS readings (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp         TEXT    NOT NULL,          -- "YYYY-MM-DD HH:MM:SS"
    voltage_v         REAL    NOT NULL,           -- Volts
    current_a         REAL    NOT NULL,           -- Amps
    power_w           REAL    NOT NULL,           -- Watts
    energy_kwh        REAL    NOT NULL,           -- cumulative kWh
    pump_status       TEXT    NOT NULL,           -- RUNNING | IDLE | BATTERY | FAULT
    fault_detected    INTEGER NOT NULL DEFAULT 0, -- 1 = fault
    power_cut         INTEGER NOT NULL DEFAULT 0, -- 1 = grid outage active
    availability_pct  REAL    NOT NULL DEFAULT 0  -- % pump uptime so far
);

-- One row per calendar day (aggregated from readings)
CREATE TABLE IF NOT EXISTS daily_summary (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    date              TEXT    UNIQUE NOT NULL,    -- "YYYY-MM-DD"
    avg_voltage_v     REAL,
    avg_current_a     REAL,
    total_energy_kwh  REAL,
    pump_hours        REAL,
    availability_pct  REAL,
    power_cuts        INTEGER DEFAULT 0,
    faults            INTEGER DEFAULT 0,
    energy_saved_kwh  REAL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_readings_ts     ON readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_readings_status ON readings(pump_status);
CREATE INDEX IF NOT EXISTS idx_daily_date      ON daily_summary(date);
"""


def init_db():
    """Create tables if they don't exist."""
    os.makedirs(os.path.dirname(config.DB_PATH), exist_ok=True)
    with get_db() as db:
        db.executescript(SCHEMA)
    print("[DB] Schema ready →", config.DB_PATH)


# ── Insert helpers ────────────────────────────────────────────────────────────

def insert_reading(r: dict):
    with get_db() as db:
        db.execute("""
            INSERT INTO readings
              (timestamp, voltage_v, current_a, power_w, energy_kwh,
               pump_status, fault_detected, power_cut, availability_pct)
            VALUES (:timestamp, :voltage_v, :current_a, :power_w, :energy_kwh,
                    :pump_status, :fault_detected, :power_cut, :availability_pct)
        """, r)


def insert_daily_summary(row: dict):
    with get_db() as db:
        db.execute("""
            INSERT OR REPLACE INTO daily_summary
              (date, avg_voltage_v, avg_current_a, total_energy_kwh,
               pump_hours, availability_pct, power_cuts, faults, energy_saved_kwh)
            VALUES (:date, :avg_voltage_v, :avg_current_a, :total_energy_kwh,
                    :pump_hours, :availability_pct, :power_cuts, :faults, :energy_saved_kwh)
        """, row)


def aggregate_day(date_str: str):
    """Aggregate a full day from readings into daily_summary."""
    with get_db() as db:
        row = db.execute("""
            SELECT
                AVG(voltage_v)                                              AS avg_v,
                AVG(current_a)                                              AS avg_a,
                MAX(energy_kwh) - MIN(energy_kwh)                          AS total_e,
                SUM(CASE WHEN pump_status IN ('RUNNING','BATTERY')
                         THEN 1 ELSE 0 END) / 3600.0                       AS pump_hrs,
                AVG(availability_pct)                                       AS avail,
                SUM(power_cut)                                              AS cuts,
                SUM(fault_detected)                                         AS faults
            FROM readings WHERE timestamp LIKE ?
        """, (f"{date_str}%",)).fetchone()

    if row and row["avg_v"]:
        insert_daily_summary({
            "date":             date_str,
            "avg_voltage_v":    round(row["avg_v"], 2),
            "avg_current_a":    round(row["avg_a"], 3),
            "total_energy_kwh": round(row["total_e"] or 0, 4),
            "pump_hours":       round(row["pump_hrs"] or 0, 2),
            "availability_pct": round(row["avail"] or 0, 1),
            "power_cuts":       int(row["cuts"] or 0),
            "faults":           int(row["faults"] or 0),
            "energy_saved_kwh": round(max(0, 1.32 - (row["total_e"] or 0)), 3),
        })
        print(f"[AGG] Daily summary saved → {date_str}")


# ── Seed historical data ──────────────────────────────────────────────────────

def seed_historical_data():
    """
    Generate SEED_DAYS of simulated readings so the dashboard
    has charts to show on first launch. Skipped if data exists.
    """
    with get_db() as db:
        count = db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
    if count > 0:
        print(f"[SEED] Data exists ({count} rows) — skipping seed")
        return

    print(f"[SEED] Generating {config.SEED_DAYS} days of historical data...")
    rng     = random.Random(42)
    energy  = config.SEED_START_ENERGY
    records = []
    base    = datetime.now() - timedelta(days=config.SEED_DAYS)
    pump_on = 0

    for sec in range(config.SEED_DAYS * 24 * 3600):
        ts     = base + timedelta(seconds=sec)

        # Simulate 30-second outage every hour
        outage = (sec % 3600) in range(1800, 1830)

        if outage:
            v       = rng.uniform(0, 4)
            i       = rng.uniform(config.BATTERY_CURRENT_MIN, config.BATTERY_CURRENT_MAX)
            p       = round(i * config.BATTERY_VOLTAGE, 1)
            status  = "BATTERY"
            pc, ft  = 1, 0
        else:
            v = rng.gauss(config.NOMINAL_VOLTAGE, config.VOLTAGE_STD)
            v = round(max(config.VOLTAGE_MIN, min(config.VOLTAGE_MAX, v)), 1)
            cycle = sec % config.PUMP_CYCLE
            if cycle < config.PUMP_ON_DURATION:
                i = rng.gauss(3.8, 0.15)
                i = round(max(config.CURRENT_RUNNING_MIN, min(config.CURRENT_RUNNING_MAX, i)), 3)
            else:
                i = round(rng.uniform(config.CURRENT_IDLE_MIN, config.CURRENT_IDLE_MAX), 3)

            ft = 1 if rng.random() < config.FAULT_PROBABILITY else 0
            if ft:
                i = round(rng.uniform(config.FAULT_CURRENT, config.FAULT_CURRENT + 0.6), 3)

            p      = round(v * i, 1)
            status = "FAULT" if ft else ("RUNNING" if i > config.PUMP_ON_CURRENT else "IDLE")
            pc     = 0

        energy += (p / 1000) / 3600
        if status in ("RUNNING", "BATTERY"):
            pump_on += 1
        avail = round((pump_on / max(sec + 1, 1)) * 100, 1)

        # Sample every N seconds to keep DB lean
        if sec % config.SEED_SAMPLE_EVERY == 0:
            records.append((
                ts.strftime("%Y-%m-%d %H:%M:%S"),
                round(v, 1), round(i, 3), p, round(energy, 5),
                status, ft, pc, avail
            ))

        # Batch insert
        if len(records) >= 5000:
            with get_db() as db:
                db.executemany("""
                    INSERT INTO readings
                    (timestamp,voltage_v,current_a,power_w,energy_kwh,
                     pump_status,fault_detected,power_cut,availability_pct)
                    VALUES (?,?,?,?,?,?,?,?,?)
                """, records)
            records.clear()

    if records:
        with get_db() as db:
            db.executemany("""
                INSERT INTO readings
                (timestamp,voltage_v,current_a,power_w,energy_kwh,
                 pump_status,fault_detected,power_cut,availability_pct)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, records)

    # Build daily summaries for seeded days
    for d in range(config.SEED_DAYS):
        day = (base + timedelta(days=d)).strftime("%Y-%m-%d")
        aggregate_day(day)

    print("[SEED] Done ✓")
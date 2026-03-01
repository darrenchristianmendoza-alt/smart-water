# api/routes.py — All REST endpoints + LLM interpretation routes

import os, sys
from flask import Blueprint, jsonify, render_template, request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from database.db import get_db
from llm.interpreter import interpreter

api_bp = Blueprint("api", __name__)


# ── Dashboard page ────────────────────────────────────────────────────────────
@api_bp.route("/")
def index():
    return render_template("index.html")


# ── Latest reading ────────────────────────────────────────────────────────────
@api_bp.route("/api/latest")
def api_latest():
    with get_db() as db:
        row = db.execute("SELECT * FROM readings ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return jsonify({"error": "No data yet"}), 404
    return jsonify(dict(row))


# ── Live chart data ───────────────────────────────────────────────────────────
@api_bp.route("/api/live")
def api_live():
    limit = min(int(request.args.get("limit", 60)), 500)
    with get_db() as db:
        rows = db.execute("""
            SELECT timestamp, voltage_v, current_a, power_w, energy_kwh,
                   pump_status, fault_detected, power_cut, availability_pct
            FROM readings ORDER BY id DESC LIMIT ?
        """, (limit,)).fetchall()
    return jsonify([dict(r) for r in reversed(rows)])


# ── Per-second table ──────────────────────────────────────────────────────────
@api_bp.route("/api/per_second")
def api_per_second():
    page   = max(int(request.args.get("page", 1)), 1)
    limit  = min(int(request.args.get("limit", 100)), 500)
    offset = (page - 1) * limit
    with get_db() as db:
        total = db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
        rows  = db.execute("""
            SELECT id, timestamp, voltage_v, current_a, power_w, energy_kwh,
                   pump_status, fault_detected, power_cut, availability_pct
            FROM readings ORDER BY id DESC LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
    return jsonify({
        "total": total, "page": page,
        "pages": max((total + limit - 1) // limit, 1),
        "limit": limit, "data": [dict(r) for r in rows],
    })


# ── Daily summary ─────────────────────────────────────────────────────────────
@api_bp.route("/api/daily")
def api_daily():
    days = min(int(request.args.get("days", 30)), 365)
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM daily_summary ORDER BY date DESC LIMIT ?", (days,)
        ).fetchall()
    return jsonify([dict(r) for r in reversed(rows)])


# ── Weekly summary ────────────────────────────────────────────────────────────
@api_bp.route("/api/weekly")
def api_weekly():
    with get_db() as db:
        rows = db.execute("""
            SELECT strftime('%Y-W%W',date) AS week,
                   MIN(date) AS week_start, MAX(date) AS week_end,
                   AVG(avg_voltage_v) AS avg_voltage, AVG(avg_current_a) AS avg_current,
                   SUM(total_energy_kwh) AS total_energy, SUM(pump_hours) AS pump_hours,
                   AVG(availability_pct) AS availability, SUM(power_cuts) AS power_cuts,
                   SUM(faults) AS faults, SUM(energy_saved_kwh) AS energy_saved
            FROM daily_summary GROUP BY week ORDER BY week DESC LIMIT 52
        """).fetchall()
    return jsonify([dict(r) for r in reversed(rows)])


# ── Monthly summary ───────────────────────────────────────────────────────────
@api_bp.route("/api/monthly")
def api_monthly():
    with get_db() as db:
        rows = db.execute("""
            SELECT strftime('%Y-%m',date) AS month, COUNT(*) AS days_recorded,
                   AVG(avg_voltage_v) AS avg_voltage, AVG(avg_current_a) AS avg_current,
                   SUM(total_energy_kwh) AS total_energy, SUM(pump_hours) AS pump_hours,
                   AVG(availability_pct) AS availability, SUM(power_cuts) AS power_cuts,
                   SUM(faults) AS faults, SUM(energy_saved_kwh) AS energy_saved
            FROM daily_summary GROUP BY month ORDER BY month DESC LIMIT 24
        """).fetchall()
    return jsonify([dict(r) for r in reversed(rows)])


# ── KPI stats ─────────────────────────────────────────────────────────────────
@api_bp.route("/api/stats")
def api_stats():
    with get_db() as db:
        total  = db.execute("SELECT COUNT(*) FROM readings").fetchone()[0]
        faults = db.execute("SELECT COUNT(*) FROM readings WHERE fault_detected=1").fetchone()[0]
        cuts   = db.execute("SELECT COUNT(*) FROM readings WHERE power_cut=1").fetchone()[0]
        avail  = db.execute("SELECT AVG(availability_pct) FROM readings").fetchone()[0]
        latest = db.execute("SELECT * FROM readings ORDER BY id DESC LIMIT 1").fetchone()
        today  = db.execute("""
            SELECT SUM(fault_detected) faults, SUM(power_cut) cuts FROM readings
            WHERE timestamp LIKE strftime('%Y-%m-%d','now') || '%'
        """).fetchone()
    return jsonify({
        "total_readings": total, "total_faults": faults, "total_power_cuts": cuts,
        "avg_availability": round(avail or 0, 1),
        "today_faults": int(today["faults"] or 0),
        "today_power_cuts": int(today["cuts"] or 0),
        "latest": dict(latest) if latest else None,
    })


# ══════════════════════════════════════════════════════════════════════════════
#  LLM ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@api_bp.route("/api/llm/status")
def llm_status():
    """Check if Ollama server is reachable."""
    return jsonify(interpreter.status())


@api_bp.route("/api/llm/interpret/daily", methods=["POST"])
def llm_daily():
    """Interpret a specific daily summary row."""
    data = request.get_json(silent=True)
    if not data:
        # Auto-fetch most recent day
        with get_db() as db:
            row = db.execute(
                "SELECT * FROM daily_summary ORDER BY date DESC LIMIT 1"
            ).fetchone()
        if not row:
            return jsonify({"error": "No daily data yet"}), 404
        data = dict(row)
    result = interpreter.interpret("daily", data)
    return jsonify(result)


@api_bp.route("/api/llm/interpret/weekly", methods=["POST"])
def llm_weekly():
    """Interpret a specific weekly summary row."""
    data = request.get_json(silent=True)
    if not data:
        with get_db() as db:
            row = db.execute("""
                SELECT strftime('%Y-W%W',date) AS week,
                       MIN(date) AS week_start, MAX(date) AS week_end,
                       AVG(avg_voltage_v) AS avg_voltage,
                       SUM(total_energy_kwh) AS total_energy,
                       SUM(pump_hours) AS pump_hours,
                       AVG(availability_pct) AS availability,
                       SUM(power_cuts) AS power_cuts,
                       SUM(faults) AS faults,
                       SUM(energy_saved_kwh) AS energy_saved
                FROM daily_summary
                GROUP BY week ORDER BY week DESC LIMIT 1
            """).fetchone()
        if not row:
            return jsonify({"error": "No weekly data yet"}), 404
        data = dict(row)
    result = interpreter.interpret("weekly", data)
    return jsonify(result)


@api_bp.route("/api/llm/interpret/monthly", methods=["POST"])
def llm_monthly():
    """Interpret a specific monthly summary row."""
    data = request.get_json(silent=True)
    if not data:
        with get_db() as db:
            row = db.execute("""
                SELECT strftime('%Y-%m',date) AS month, COUNT(*) AS days_recorded,
                       AVG(avg_voltage_v) AS avg_voltage,
                       SUM(total_energy_kwh) AS total_energy,
                       SUM(pump_hours) AS pump_hours,
                       AVG(availability_pct) AS availability,
                       SUM(power_cuts) AS power_cuts,
                       SUM(faults) AS faults,
                       SUM(energy_saved_kwh) AS energy_saved
                FROM daily_summary
                GROUP BY month ORDER BY month DESC LIMIT 1
            """).fetchone()
        if not row:
            return jsonify({"error": "No monthly data yet"}), 404
        data = dict(row)
    result = interpreter.interpret("monthly", data)
    return jsonify(result)
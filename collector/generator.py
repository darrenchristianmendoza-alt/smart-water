# collector/generator.py
# Simulates a Peacefair power meter generating per-second readings.
# In production: replace _read() with actual Modbus/RS485 calls.

import os
import sys
import random
import threading
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from database.db import insert_reading, aggregate_day


class DataGenerator:
    """
    Background thread that generates (or reads) one sensor sample per second
    and persists it to SQLite.

    Simulated signals:
        Voltage  → Gaussian noise around 218 V; drops to ~0 V during outage
        Current  → Cycles between running (3.2–4.4 A) and idle (0–0.08 A)
        Power    → Voltage × Current
        Energy   → Cumulative kWh (incremented each second)

    Derived fields (no extra sensor needed):
        pump_status      → RUNNING / IDLE / BATTERY / FAULT
        fault_detected   → 1 if current > fault threshold
        power_cut        → 1 if voltage < power-cut threshold
        availability_pct → pump-on seconds / total seconds × 100
    """

    def __init__(self):
        self._running       = False
        self._thread        = None
        self._rng           = random.Random()   # unseeded = truly random each run
        self._energy_kwh    = config.SEED_START_ENERGY
        self._pump_on_sec   = 0
        self._total_sec     = 0
        self._in_outage     = False
        self._outage_start  = None
        self._outage_dur    = 0
        self._next_outage   = time.time() + self._rng.randint(
                                  config.OUTAGE_MIN_INTERVAL,
                                  config.OUTAGE_MAX_INTERVAL)
        self._last_day      = datetime.now().day

    # ── Public API ────────────────────────────────────────────────────────────

    def start(self):
        """Start background collection thread."""
        self._running = True
        self._thread  = threading.Thread(target=self._loop, name="DataCollector", daemon=True)
        self._thread.start()
        print("[GEN] Data generator started (1 reading/second)")

    def stop(self):
        """Gracefully stop the collection thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        print("[GEN] Data generator stopped")

    # ── Private ───────────────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            tick = time.time()

            reading = self._read()        # Generate one sample
            insert_reading(reading)       # Persist to SQLite

            # Daily rollover → aggregate yesterday
            today = datetime.now().day
            if today != self._last_day:
                yesterday = datetime.now().replace(day=self._last_day)
                aggregate_day(yesterday.strftime("%Y-%m-%d"))
                self._last_day = today

            # Sleep exactly 1 second minus processing time
            elapsed = time.time() - tick
            time.sleep(max(0, config.COLLECT_INTERVAL_SEC - elapsed))

    def _read(self) -> dict:
        """
        Generate one simulated reading.
        To use real hardware, replace the body of this method with
        Modbus register reads from the Peacefair meter.
        """
        now = time.time()

        # ── Outage logic ──────────────────────────────────────────────────────
        if not self._in_outage and now >= self._next_outage:
            self._in_outage    = True
            self._outage_start = now
            self._outage_dur   = self._rng.randint(
                config.OUTAGE_MIN_DURATION, config.OUTAGE_MAX_DURATION)
            print(f"[SIM] ⚡ Power cut! Duration ≈ {self._outage_dur}s")

        if self._in_outage and (now - self._outage_start) >= self._outage_dur:
            self._in_outage = False
            self._next_outage = now + self._rng.randint(
                config.OUTAGE_MIN_INTERVAL, config.OUTAGE_MAX_INTERVAL)
            print("[SIM] ✅ Power restored")

        # ── Voltage ───────────────────────────────────────────────────────────
        if self._in_outage:
            voltage = round(self._rng.uniform(0, 4), 1)
        else:
            voltage = round(self._rng.gauss(config.NOMINAL_VOLTAGE, config.VOLTAGE_STD), 1)
            voltage = max(config.VOLTAGE_MIN, min(config.VOLTAGE_MAX, voltage))

        # ── Current ───────────────────────────────────────────────────────────
        if self._in_outage:
            # Pump running on battery backup
            current = round(self._rng.uniform(
                config.BATTERY_CURRENT_MIN, config.BATTERY_CURRENT_MAX), 3)
            fault = 0
        else:
            # Pump duty cycle: on for PUMP_ON_DURATION, off for PUMP_OFF_DURATION
            cycle_pos = self._total_sec % config.PUMP_CYCLE
            if cycle_pos < config.PUMP_ON_DURATION:
                current = round(self._rng.gauss(3.8, 0.15), 3)
                current = max(config.CURRENT_RUNNING_MIN,
                              min(config.CURRENT_RUNNING_MAX, current))
            else:
                current = round(self._rng.uniform(
                    config.CURRENT_IDLE_MIN, config.CURRENT_IDLE_MAX), 3)

            # Random fault spike
            fault = 1 if self._rng.random() < config.FAULT_PROBABILITY else 0
            if fault:
                current = round(self._rng.uniform(
                    config.FAULT_CURRENT, config.FAULT_CURRENT + 0.6), 3)

        # ── Power & Energy ────────────────────────────────────────────────────
        if self._in_outage:
            power = round(current * config.BATTERY_VOLTAGE, 1)
        else:
            power = round(voltage * current, 1)

        self._energy_kwh += (power / 1000) / 3600   # Wh → kWh per second
        self._energy_kwh  = round(self._energy_kwh, 5)

        # ── Derived fields ────────────────────────────────────────────────────
        self._total_sec += 1
        pump_status = (
            "FAULT"   if fault else
            "BATTERY" if self._in_outage else
            "RUNNING" if current > config.PUMP_ON_CURRENT else
            "IDLE"
        )
        if pump_status in ("RUNNING", "BATTERY"):
            self._pump_on_sec += 1

        availability = round((self._pump_on_sec / self._total_sec) * 100, 1)

        # ── Battery remaining time estimate ───────────────────────────────────
        battery_time = None
        if self._in_outage and current > 0:
            battery_time = round(
                (config.BATTERY_CAPACITY_AH * config.BATTERY_DOD) / current, 2)

        return {
            "timestamp":        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "voltage_v":        voltage,
            "current_a":        current,
            "power_w":          power,
            "energy_kwh":       self._energy_kwh,
            "pump_status":      pump_status,
            "fault_detected":   fault,
            "power_cut":        1 if self._in_outage else 0,
            "availability_pct": availability,
            # extra fields for live API (not stored in DB)
            "_battery_time_hrs": battery_time,
            "_total_sec":        self._total_sec,
        }
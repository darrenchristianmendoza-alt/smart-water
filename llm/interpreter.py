# llm/interpreter.py
# Connects to Ollama/Mistral running on Google Colab via ngrok tunnel
# and returns plain-English interpretations of analytics data.

import os, sys, json, requests, logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

logger = logging.getLogger("SmartWater.LLM")

# =============================================================================
#  PROMPT TEMPLATES  — one per analytics type
# =============================================================================
PROMPTS = {

"live": """You are an expert analyst for a solar-powered smart water pump system in the Philippines.
Analyze this REAL-TIME sensor reading and give a SHORT, clear interpretation in 2-3 sentences.
Focus on current system state and whether anything needs immediate attention.

Real-time Reading:
- Voltage:      {voltage_v} V     (normal: 210–230 V)
- Current:      {current_a} A     (running: 3.2–4.4 A | idle: <0.5 A | fault: >4.6 A)
- Power:        {power_w} W
- Energy:       {energy_kwh} kWh  (cumulative meter reading)
- Pump Status:  {pump_status}     (RUNNING / IDLE / BATTERY / FAULT)
- Availability: {availability_pct}%
- Fault:        {fault_detected}
- Power Cut:    {power_cut}

Be concise. If fault or power cut is active, state it first with urgency.""",

"daily": """You are an expert analyst for a solar-powered smart water pump system in the Philippines (BATELEC grid area).
Analyze this DAILY SUMMARY and give a 3–4 sentence interpretation covering:
system health, pump performance vs targets, energy efficiency, and any concerns.

Daily Summary — {date}:
- Avg Voltage:       {avg_voltage_v} V
- Avg Current:       {avg_current_a} A
- Total Energy Used: {total_energy_kwh} kWh  (baseline without smart system: 1.32 kWh/day)
- Pump Hours:        {pump_hours} hrs        (target: 7–8 hrs/day)
- Availability:      {availability_pct}%     (target ≥76.5% | without system: 47%)
- Power Cuts:        {power_cuts}
- Faults Detected:   {faults}
- Energy Saved:      {energy_saved_kwh} kWh

State clearly whether daily targets were met. Use specific numbers.""",

"weekly": """You are an expert analyst for a solar-powered smart water pump system in the Philippines.
Analyze this WEEKLY SUMMARY and give a 3–4 sentence interpretation covering:
performance trends, comparison to targets, and one actionable recommendation.

Weekly Summary — {week} ({week_start} to {week_end}):
- Avg Voltage:       {avg_voltage} V
- Total Energy Used: {total_energy} kWh   (target: ~9.24 kWh/week)
- Total Pump Hours:  {pump_hours} hrs     (target: 49–56 hrs/week)
- Avg Availability:  {availability}%      (target ≥76.5%)
- Total Power Cuts:  {power_cuts}
- Total Faults:      {faults}
- Total Energy Saved:{energy_saved} kWh

Identify trends and give one specific recommendation.""",

"monthly": """You are an expert analyst for a solar-powered smart water pump system in the Philippines.
Analyze this MONTHLY SUMMARY and give a 4–5 sentence interpretation covering:
overall performance, reliability, energy savings, and a recommendation for next month.

Monthly Summary — {month}:
- Days Recorded:     {days_recorded}
- Avg Voltage:       {avg_voltage} V
- Total Energy Used: {total_energy} kWh
- Total Pump Hours:  {pump_hours} hrs
- Avg Availability:  {availability}%   (target ≥76.5% | without system: 47%)
- Total Power Cuts:  {power_cuts}
- Total Faults:      {faults}
- Total Energy Saved:{energy_saved} kWh

Compare to targets. Highlight reliability and energy savings. Give one concrete recommendation.""",

}


# =============================================================================
#  OLLAMA CLIENT
# =============================================================================
class OllamaInterpreter:
    """Sends analytics data to Mistral via the ngrok tunnel from Google Colab."""

    def __init__(self):
        self.base_url = config.OLLAMA_URL.rstrip("/")
        self.model    = config.OLLAMA_MODEL
        self.timeout  = config.OLLAMA_TIMEOUT

    # ── Public ────────────────────────────────────────────────────────────────

    def interpret(self, analytics_type: str, data: dict) -> dict:
        """Build prompt, call Mistral, return result dict."""
        if analytics_type not in PROMPTS:
            return self._err(f"Unknown type: {analytics_type}")
        try:
            prompt = PROMPTS[analytics_type].format(**self._clean(data))
        except KeyError as e:
            return self._err(f"Missing field in data: {e}")
        try:
            r = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model":  self.model,
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.3, "top_p": 0.9, "num_predict": 350}
                },
                timeout=self.timeout,
                headers={"Content-Type": "application/json",
                         "ngrok-skip-browser-warning": "true"}
            )
            if r.status_code != 200:
                return self._err(f"Ollama HTTP {r.status_code}: {r.text[:200]}")
            text = r.json().get("response", "").strip()
            if not text:
                return self._err("Empty response from model")
            logger.info(f"LLM [{analytics_type}] OK — {len(text)} chars")
            return {"success": True, "interpretation": text,
                    "model": self.model, "type": analytics_type, "error": None}
        except requests.exceptions.Timeout:
            return self._err(f"Request timed out after {self.timeout}s. Is Colab still running?")
        except requests.exceptions.ConnectionError:
            return self._err(f"Cannot connect to {self.base_url}. Update OLLAMA_URL in config.py.")
        except Exception as e:
            return self._err(str(e))

    def status(self) -> dict:
        """Check if Ollama server is reachable."""
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=6,
                             headers={"ngrok-skip-browser-warning": "true"})
            if r.status_code == 200:
                models = [m["name"] for m in r.json().get("models", [])]
                return {"connected": True, "url": self.base_url,
                        "model": self.model, "models": models}
        except Exception:
            pass
        return {"connected": False, "url": self.base_url,
                "model": self.model, "models": []}

    # ── Private ───────────────────────────────────────────────────────────────

    def _clean(self, d: dict) -> dict:
        out = {}
        for k, v in d.items():
            if v is None:        out[k] = "N/A"
            elif isinstance(v, float): out[k] = round(v, 3)
            else:                out[k] = v
        return out

    def _err(self, msg: str) -> dict:
        logger.warning(f"LLM error: {msg}")
        return {"success": False, "interpretation": None,
                "model": self.model, "type": None, "error": msg}


# Singleton
interpreter = OllamaInterpreter()
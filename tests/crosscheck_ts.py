"""Vergleicht die Python-Portierung mit der TypeScript-Referenz.

Beide dekodieren dieselben aufgezeichneten Payloads; die Ergebnisse muessen
identisch sein. Kein pytest, sondern ein manuelles Werkzeug - es braucht die
Node-Umgebung des ioBroker-Adapters.

    python tests/crosscheck_ts.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from custom_components.ecoflow_ocean2.protobuf import decode_mqtt_payload  # noqa: E402
from tests.test_protobuf import PCS_BLOCK_HEX, SUMMARY_HEX  # noqa: E402

TS_PROJECT = Path("F:/Developments/ioBroker.ecoflow-powerocean")

TS_SCRIPT = """
import { decodeMqttPayload } from './src/lib/protobuf';
const hexes = process.argv.slice(2);
const out = hexes.map((hex) => {
  const raw = new Uint8Array(hex.match(/.{2}/g).map((b) => parseInt(b, 16)));
  const m = decodeMqttPayload(raw);
  const t = m.po2Telemetry;
  return t
    ? {
        pv: t.pvPowerW, grid: t.gridPowerW, battery: t.batteryPowerW,
        soc: t.socPercent, remaining: t.remainingWh, pcs: t.pcsTotalW,
        phases: [...t.phases.entries()].sort(),
        strings: [...t.pvStrings.entries()].sort(),
      }
    : null;
});
console.log(JSON.stringify(out));
"""


def python_result(hex_payload: str) -> dict | None:
    message = decode_mqtt_payload(bytes.fromhex(hex_payload))
    t = message.po2_telemetry
    if t is None:
        return None
    return {
        "pv": t.pv_power_w,
        "grid": t.grid_power_w,
        "battery": t.battery_power_w,
        "soc": t.soc_percent,
        "remaining": t.remaining_wh,
        "pcs": t.pcs_total_w,
        "phases": sorted(
            [index, dict(sorted(values.items()))] for index, values in t.phases.items()
        ),
        "strings": sorted([index, value] for index, value in t.pv_strings.items()),
    }


# TS nutzt andere Feldnamen in den Phasen-Objekten - hier angleichen
_TS_TO_PY = {
    "vol": "vol",
    "amp": "amp",
    "actPwr": "act_pwr",
    "reactPwr": "react_pwr",
    "apparentPwr": "apparent_pwr",
}


def normalise_ts(entry: dict | None) -> dict | None:
    if entry is None:
        return None
    entry = dict(entry)
    entry["phases"] = sorted(
        [index, {_TS_TO_PY[k]: v for k, v in sorted(values.items())}]
        for index, values in entry["phases"]
    )
    entry["strings"] = sorted([index, value] for index, value in entry["strings"])
    return entry


def approx_equal(a, b, tolerance: float = 1e-6) -> bool:
    """Vergleicht rekursiv, Zahlen mit Toleranz (float32 vs. float64)."""
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= max(tolerance, abs(b) * 1e-9)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(approx_equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(approx_equal(x, y) for x, y in zip(a, b))
    return a == b


def main() -> int:
    payloads = [SUMMARY_HEX, PCS_BLOCK_HEX]
    script = TS_PROJECT / "crosscheck.tmp.ts"
    script.write_text(TS_SCRIPT, encoding="utf-8")
    try:
        proc = subprocess.run(
            ["npx", "tsx", str(script), *payloads],
            cwd=TS_PROJECT,
            capture_output=True,
            text=True,
            shell=True,
            check=True,
        )
    finally:
        script.unlink(missing_ok=True)

    ts_results = json.loads(proc.stdout.strip().splitlines()[-1])

    failures = 0
    for name, hex_payload, ts_raw in zip(
        ("SUMMARY", "PCS_BLOCK"), payloads, ts_results
    ):
        py = python_result(hex_payload)
        ts = normalise_ts(ts_raw)
        if approx_equal(py, ts):
            print(f"[OK]   {name}: Python == TypeScript")
        else:
            failures += 1
            print(f"[FEHLER] {name}:")
            print("  Python    :", json.dumps(py, sort_keys=True))
            print("  TypeScript:", json.dumps(ts, sort_keys=True))

    print()
    print("Ergebnis:", "identisch" if not failures else f"{failures} Abweichung(en)")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

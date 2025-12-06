"""
Central config/constants for PT generation.
Requires a user-defined instrument setup JSON (instruments.json by default,
override with INSTRUMENT_CONFIG env var).
"""

from typing import Tuple, Dict, List, Any
import json, os, pathlib

# Base URL of your DCN API.
API_BASE: str = "https://api.decentralised.art"

BASE_DIR = pathlib.Path(__file__).resolve().parent

def _load_instrument_config_from_file(path: pathlib.Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def _normalize_instr_block(raw: Dict[str, Any]) -> Dict[str, Dict[str, tuple]]:
    out: Dict[str, Dict[str, tuple]] = {}
    for name, meta in raw.items():
        rng = tuple(meta.get("range", (0, 0)))
        tess = tuple(meta.get("tess", meta.get("tessitura", rng)))
        poly = bool(meta.get("polyphonic", False))
        if len(rng) != 2:
            raise ValueError(f"Instrument {name} must have range [lo, hi]")
        out[name] = {"range": (int(rng[0]), int(rng[1])), "tess": (int(tess[0]), int(tess[1])), "polyphonic": poly}
    return out

def _normalize_meta_block(raw: Dict[str, Any], instruments: Dict[str, Dict[str, tuple]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for name in instruments.keys():
        base = raw.get(name, {}) if isinstance(raw, dict) else {}
        out[name] = {
            "display_name": base.get("display_name") or name.replace("_", " ").title(),
            "gm_program": base.get("gm_program"),
            "bank": base.get("bank", base.get("bank_msb", 0)),
            "bank_msb": base.get("bank_msb", base.get("bank", 0)),
            "bank_lsb": base.get("bank_lsb", 0),
        }
    return out

def load_instrument_setup(config_path: str | pathlib.Path | None = None) -> tuple[list[str], Dict[str, Dict[str, tuple]], Dict[str, Dict[str, Any]]]:
    """
    Load instrument order + ranges + meta from a JSON config.
    Shape of instruments.json:
      {
        "ordered_instruments": ["violin", "cello"],      // optional; defaults to file key order
        "instruments": {
            "violin": {"range": [55, 88], "tess": [60, 84], "display_name": "Violin", "gm_program": 40},
            ...
        },
        "instrument_meta": { ... }   // optional overrides
      }
    If the file is missing or invalid, fall back to built-in defaults.
    """
    cfg_path = pathlib.Path(config_path).expanduser() if config_path else None
    if cfg_path is None:
        env = os.getenv("INSTRUMENT_CONFIG")
        if env:
            cfg_path = pathlib.Path(env).expanduser()
        else:
            cfg_path = BASE_DIR / "instruments.json"

    if not cfg_path.exists():
        raise RuntimeError(f"Instrument config not found: {cfg_path}. Provide instruments.json or set INSTRUMENT_CONFIG.")

    data = _load_instrument_config_from_file(cfg_path)
    if not isinstance(data, dict):
        raise ValueError("Instrument config root must be an object")

    if "instruments" not in data or not isinstance(data["instruments"], dict) or not data["instruments"]:
        raise ValueError("Instrument config must include a non-empty 'instruments' object")

    instruments = _normalize_instr_block(data["instruments"])
    meta = _normalize_meta_block(data.get("instrument_meta", {}), instruments)

    if "ordered_instruments" in data and isinstance(data["ordered_instruments"], list):
        order = [str(i) for i in data["ordered_instruments"] if str(i) in instruments]
    else:
        order = list(instruments.keys())

    # Ensure order covers all instruments (preserve explicit order first)
    seen = set(order)
    for name in instruments.keys():
        if name not in seen:
            order.append(name)
            seen.add(name)

    if not order:
        raise ValueError("No instruments defined after processing instrument config")

    return order, instruments, meta


# Expose loaded setup as module-level values for convenience
ORDERED_INSTRS, INSTRUMENTS, INSTRUMENT_META = load_instrument_setup()

# Optional: ticks per bar per bar-index (expand as you add bars).
# 1 tick = 1/16 note; 12 means 3/4 with 16th grid.
BAR_TICKS_BY_BAR = {
    1: 12,   # 3/4
    2: 8,    # 2/4  (example)
    3: 16,   # 4/4  (example)
}

def meter_from_ticks(ticks: int) -> Tuple[int, int]:
    """
    Map ticks to (numerator, denominator).
    Extend this dict if you use other metres on a 16th grid.
    """
    return {12:(3,4), 8:(2,4), 16:(4,4), 4:(1,4)}.get(int(ticks), (4,4))


def instruments_summary_lines(order: List[str] | None = None,
                              instruments: Dict[str, Dict[str, tuple]] | None = None) -> List[str]:
    """Helper to render a readable instrument block for prompts/logs."""
    order = order or ORDERED_INSTRS
    instruments = instruments or INSTRUMENTS
    lines = []
    for name in order:
        meta = instruments.get(name, {})
        rng = meta.get("range", ("?", "?"))
        poly = "polyphonic" if meta.get("polyphonic") else "monophonic"
        lines.append(f"- {name}: [{rng[0]}..{rng[1]}] ({poly})")
    return lines

def is_polyphonic(instrument: str) -> bool:
    return bool(INSTRUMENTS.get(instrument, {}).get("polyphonic", False))

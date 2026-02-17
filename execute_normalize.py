"""Helpers for particle execution payloads and execute-response normalization."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Tuple
import re

SCALAR_BY_DIM_ID: Dict[int, str] = {
    0: "time",
    1: "duration",
    2: "pitch",
    3: "velocity",
    4: "numerator",
    5: "denominator",
}

REQUIRED_SCALARS = ("time", "duration", "pitch", "velocity", "numerator", "denominator")


def build_running_instances(seeds: Dict[str, int], dims: List[dict]) -> List[Dict[str, int]]:
    """
    Build running_instances for /execute:
      - index 0: root start point (time seed)
      - index 1..N: one item per feature dimension in declared order
    """
    running_instances: List[Dict[str, int]] = [{
        "start_point": int(seeds.get("time", 0)),
        "transformation_shift": 0,
    }]

    for dim in dims:
        feature_name = (dim.get("feature_name") or "").strip().lower()
        running_instances.append({
            "start_point": int(seeds.get(feature_name, 0)),
            "transformation_shift": 0,
        })

    return running_instances


def _parse_dim_id_from_path(path: str) -> int | None:
    if not path:
        return None
    match = re.search(r":(\d+)$", path.strip())
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _coerce_int_list(values: Any) -> List[int]:
    if not isinstance(values, list):
        return []
    out: List[int] = []
    for value in values:
        try:
            out.append(int(value))
        except Exception:
            continue
    return out


def normalize_execute_samples(samples_list: List[dict]) -> Tuple[Dict[str, List[int]], List[str]]:
    """
    Normalize execute output into scalar streams.

    Supported sample shapes:
      - Current server: {"path": "/particle_name:2", "data": [...]}  (dim-id mapping)
      - Legacy fallback: {"feature_path": "/x/y/pitch", "data": [...]} (tail-name mapping)
    """
    streams: Dict[str, List[int]] = {}
    unknown_paths: List[str] = []

    for sample in samples_list:
        path = str(sample.get("path") or sample.get("feature_path") or "").strip()
        data = _coerce_int_list(sample.get("data", []))

        if path:
            dim_id = _parse_dim_id_from_path(path)
            if dim_id is not None and dim_id in SCALAR_BY_DIM_ID:
                streams[SCALAR_BY_DIM_ID[dim_id]] = data
                continue

            tail = path.split("/")[-1].strip().lower()
            if tail in REQUIRED_SCALARS:
                streams[tail] = data
                continue

            unknown_paths.append(path)
            continue

        unknown_paths.append("<missing path>")

    return streams, unknown_paths


def require_scalar_streams(streams: Dict[str, List[int]], *, label: str, unknown_paths: Iterable[str]) -> None:
    missing = [scalar for scalar in REQUIRED_SCALARS if scalar not in streams]
    if not missing:
        return

    unknown = [p for p in unknown_paths if p]
    unknown_preview = ", ".join(unknown[:8])
    if len(unknown) > 8:
        unknown_preview += ", ..."

    raise RuntimeError(
        f"[{label}] Missing execute scalar streams: {missing}. "
        f"Received keys={sorted(streams.keys())}. "
        f"Unmapped paths={unknown_preview or 'none'}"
    )

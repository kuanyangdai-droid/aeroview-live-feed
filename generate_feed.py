#!/usr/bin/env python3
"""
AeroView Special Livery Live Feed Generator

This script queries AirLabs Real-Time Flights API for live flights involving
selected China airports, cross-matches returned aircraft registration numbers
against special_liveries.json, and writes a static JSON feed for GoDaddy or
any frontend widget to consume.

Required environment variable:
  AIRLABS_API_KEY

Optional environment variables:
  TARGET_AIRPORTS   Comma-separated IATA airport codes.
  OUTPUT_PATH       Default: public/special-livery-live.json
  META_PATH         Default: public/feed-meta.json
  DEMO_MODE         If true, writes demo records without calling AirLabs.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

AIRLABS_ENDPOINT = "https://airlabs.co/api/v9/flights"
DEFAULT_TARGET_AIRPORTS = ["PVG", "SHA", "PEK", "PKX", "SZX", "CAN", "HGH", "CTU", "TFU", "DLC"]
DEFAULT_OUTPUT_PATH = Path("public/special-livery-live.json")
DEFAULT_META_PATH = Path("public/feed-meta.json")
SPECIAL_LIVERIES_PATH = Path("special_liveries.json")
REQUEST_SLEEP_SECONDS = 0.75
REQUEST_TIMEOUT_SECONDS = 30
MAX_RECORDS = 80
CHINA_TZ = timezone(timedelta(hours=8))


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_datetime(value: Any) -> Optional[datetime]:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def local_date_key(value: Any, tz: timezone = CHINA_TZ) -> Optional[str]:
    parsed = parse_iso_datetime(value)
    if not parsed:
        return None
    return parsed.astimezone(tz).date().isoformat()


def normalize_registration(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper().replace(" ", "").replace("_", "-")


def normalize_iata(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def load_special_liveries(path: Path = SPECIAL_LIVERIES_PATH) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Special livery database not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("special_liveries.json must be a JSON array")

    result: Dict[str, Dict[str, Any]] = {}
    for item in data:
        reg = normalize_registration(item.get("registration"))
        if not reg:
            continue
        clean_item = dict(item)
        clean_item["registration"] = reg
        result[reg] = clean_item
    return result


def get_target_airports() -> List[str]:
    raw = os.environ.get("TARGET_AIRPORTS", "")
    if raw.strip():
        airports = [normalize_iata(x) for x in raw.split(",") if normalize_iata(x)]
        return airports
    return DEFAULT_TARGET_AIRPORTS


def request_airlabs(api_key: str, params: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    query = dict(params)
    query["api_key"] = api_key
    url = AIRLABS_ENDPOINT + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"User-Agent": "AeroViewLiveFeed/1.0"})

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - keep workflow robust and report in metadata
        return [], f"request_failed: {type(exc).__name__}: {exc}"

    if isinstance(payload, dict) and payload.get("error"):
        return [], f"api_error: {payload.get('error')}"

    records = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return [], "invalid_response: missing response array"
    return records, None


def fetch_realtime_flights(api_key: str, target_airports: Iterable[str]) -> Tuple[List[Dict[str, Any]], List[str]]:
    all_flights: List[Dict[str, Any]] = []
    errors: List[str] = []

    for airport in target_airports:
        for direction_field in ("dep_iata", "arr_iata"):
            params = {direction_field: airport}
            records, error = request_airlabs(api_key, params)
            if error:
                errors.append(f"{direction_field}={airport}: {error}")
            else:
                all_flights.extend(records)
            time.sleep(REQUEST_SLEEP_SECONDS)
    return all_flights, errors


def pick_first(record: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return default


def to_number_or_none(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_status(value: Any) -> str:
    status = str(value or "").strip().lower()
    if status in {"landed", "arrived", "arrival", "arr", "on-ground", "onground"}:
        return "landed"
    return status or "en-route"


def convert_flight_record(
    flight: Dict[str, Any],
    livery: Dict[str, Any],
    target_airports: set[str],
    generated_at: str,
) -> Optional[Dict[str, Any]]:
    dep = normalize_iata(pick_first(flight, ["dep_iata", "dep_icao"]))
    arr = normalize_iata(pick_first(flight, ["arr_iata", "arr_icao"]))
    if dep not in target_airports and arr not in target_airports:
        return None

    registration = normalize_registration(pick_first(flight, ["reg_number", "registration", "reg"]))
    flight_iata = pick_first(flight, ["flight_iata", "flight_number", "flight_icao"], "")
    airline_name = pick_first(flight, ["airline_name"], livery.get("airline", ""))
    aircraft = pick_first(flight, ["aircraft_icao", "aircraft_code"], livery.get("aircraft", ""))
    altitude = to_number_or_none(pick_first(flight, ["alt", "altitude"]))
    speed = to_number_or_none(pick_first(flight, ["speed", "gs", "ground_speed"]))
    lat = to_number_or_none(flight.get("lat"))
    lng = to_number_or_none(flight.get("lng"))

    updated_raw = pick_first(flight, ["updated", "timestamp"], None)
    updated_iso = generated_at
    if isinstance(updated_raw, (int, float)):
        try:
            updated_iso = datetime.fromtimestamp(float(updated_raw), tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        except Exception:
            updated_iso = generated_at

    return {
        "flight": str(flight_iata or "Unknown").upper(),
        "airline": airline_name or livery.get("airline", ""),
        "aircraft": aircraft or livery.get("aircraft", ""),
        "registration": registration,
        "livery": livery.get("livery", "Special Livery"),
        "origin": dep or "",
        "destination": arr or "",
        "altitude_m": altitude,
        "speed_kmh": speed,
        "latitude": lat,
        "longitude": lng,
        "status": normalize_status(pick_first(flight, ["status"], "en-route")),
        "updated": updated_iso,
        "source": "AirLabs Real-Time Flights + special_liveries.json",
    }


def feed_key(row: Dict[str, Any]) -> str:
    return "|".join([row.get("registration", ""), row.get("flight", ""), row.get("origin", ""), row.get("destination", "")])


def is_today_record(row: Dict[str, Any], generated_at: str) -> bool:
    today = local_date_key(generated_at)
    return bool(today and local_date_key(row.get("updated")) == today)


def mark_as_landed(row: Dict[str, Any], generated_at: str) -> Dict[str, Any]:
    landed = dict(row)
    landed["status"] = "landed"
    landed["altitude_m"] = 0
    landed["speed_kmh"] = 0
    landed["updated"] = generated_at
    landed["source"] = "Retained from previous feed after landing"
    return landed


def merge_landed_today(
    rows: List[Dict[str, Any]],
    previous_rows: List[Dict[str, Any]],
    generated_at: str,
) -> List[Dict[str, Any]]:
    seen = {feed_key(row) for row in rows}
    merged = list(rows)

    for previous in previous_rows:
        if not isinstance(previous, dict):
            continue
        key = feed_key(previous)
        if not key or key in seen:
            continue
        if not is_today_record(previous, generated_at):
            continue
        seen.add(key)
        merged.append(mark_as_landed(previous, generated_at))

    return merged


def build_feed(
    flights: List[Dict[str, Any]],
    special_liveries: Dict[str, Dict[str, Any]],
    target_airports: List[str],
    previous_rows: Optional[List[Dict[str, Any]]] = None,
    generated_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    generated_at = generated_at or utc_now_iso()
    target_set = set(target_airports)
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for flight in flights:
        reg = normalize_registration(pick_first(flight, ["reg_number", "registration", "reg"]))
        if not reg or reg not in special_liveries:
            continue
        row = convert_flight_record(flight, special_liveries[reg], target_set, generated_at)
        if not row:
            continue
        key = feed_key(row)
        if key in seen:
            continue
        seen.add(key)
        rows.append(row)

    if previous_rows:
        rows = merge_landed_today(rows, previous_rows, generated_at)

    rows.sort(key=lambda x: (x.get("updated") or "", x.get("flight") or ""), reverse=True)
    return rows[:MAX_RECORDS]


def demo_feed() -> List[Dict[str, Any]]:
    now = utc_now_iso()
    return [
        {
            "flight": "CA123",
            "airline": "Air China",
            "aircraft": "Boeing 777-300ER",
            "registration": "B-2006",
            "livery": "Love China",
            "origin": "PEK",
            "destination": "PVG",
            "altitude_m": 9800,
            "speed_kmh": 850,
            "latitude": 35.1,
            "longitude": 117.2,
            "status": "en-route",
            "updated": now,
            "source": "Demo data",
        },
        {
            "flight": "MU512",
            "airline": "China Eastern Airlines",
            "aircraft": "Airbus A330-200",
            "registration": "B-5949",
            "livery": "SkyTeam",
            "origin": "SHA",
            "destination": "HKG",
            "altitude_m": 10600,
            "speed_kmh": 820,
            "latitude": 27.4,
            "longitude": 115.8,
            "status": "en-route",
            "updated": now,
            "source": "Demo data",
        },
    ]


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_previous_feed_url() -> str:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not repository or "/" not in repository:
        return ""
    owner, repo = repository.split("/", 1)
    return f"https://{owner}.github.io/{repo}/special-livery-live.json"


def load_json_array_from_url(url: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "AeroViewLiveFeed/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - previous feed is best effort
        return [], f"previous_feed_failed: {type(exc).__name__}: {exc}"
    if not isinstance(payload, list):
        return [], "previous_feed_invalid: expected JSON array"
    return [item for item in payload if isinstance(item, dict)], None


def load_previous_feed(output_path: Path) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    if output_path.exists():
        try:
            payload = json.loads(output_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return [], f"previous_feed_file_failed: {type(exc).__name__}: {exc}"
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)], None
        return [], "previous_feed_file_invalid: expected JSON array"

    previous_url = os.environ.get("PREVIOUS_FEED_URL", "").strip() or default_previous_feed_url()
    if not previous_url:
        return [], None
    return load_json_array_from_url(previous_url)


def main() -> int:
    output_path = Path(os.environ.get("OUTPUT_PATH", str(DEFAULT_OUTPUT_PATH)))
    meta_path = Path(os.environ.get("META_PATH", str(DEFAULT_META_PATH)))
    target_airports = get_target_airports()
    generated_at = utc_now_iso()
    errors: List[str] = []
    demo_mode = os.environ.get("DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}

    try:
        special_liveries = load_special_liveries()
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to load special_liveries.json: {exc}", file=sys.stderr)
        return 2

    if demo_mode:
        feed = demo_feed()
    else:
        api_key = os.environ.get("AIRLABS_API_KEY", "").strip()
        if not api_key:
            print("AIRLABS_API_KEY is required unless DEMO_MODE=true", file=sys.stderr)
            return 2
        previous_feed, previous_feed_error = load_previous_feed(output_path)
        if previous_feed_error:
            errors.append(previous_feed_error)
        flights, fetch_errors = fetch_realtime_flights(api_key, target_airports)
        errors.extend(fetch_errors)
        feed = build_feed(flights, special_liveries, target_airports, previous_feed, generated_at)

    meta = {
        "generated_at": generated_at,
        "target_airports": target_airports,
        "record_count": len(feed),
        "special_livery_count": len(special_liveries),
        "mode": "demo" if demo_mode else "live",
        "errors": errors[:50],
        "notes": "Feed contains only currently tracked flights whose registration number is returned by the API and exists in special_liveries.json.",
    }

    write_json(output_path, feed)
    write_json(meta_path, meta)
    print(f"Wrote {len(feed)} records to {output_path}")
    print(f"Wrote metadata to {meta_path}")
    if errors:
        print("Warnings:")
        for err in errors[:10]:
            print(f"- {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

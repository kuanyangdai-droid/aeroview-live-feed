#!/usr/bin/env python3
"""
AeroView Hangzhou special livery schedule scanner.

The feed is intentionally narrow:
- one airport, Hangzhou Xiaoshan (HGH) by default
- today's scheduled arrivals and departures
- only rows where AirLabs returns a concrete aircraft registration
- registrations are matched against special_liveries.json

Required environment variable:
  AIRLABS_API_KEY

Optional environment variables:
  TRACK_AIRPORT      IATA airport code. Default: HGH
  SCHEDULE_DATE      YYYY-MM-DD in Asia/Shanghai. Default: today
  OUTPUT_PATH        Default: public/special-livery-live.json
  META_PATH          Default: public/feed-meta.json
  PREVIOUS_FEED_URL  Optional previous JSON feed URL for same-day retention
  DEMO_MODE          If true, writes demo records without calling AirLabs
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

AIRLABS_SCHEDULES_ENDPOINT = "https://airlabs.co/api/v9/schedules"
SCHEDULE_SOURCE = "AirLabs Schedules + special_liveries.json"
DEFAULT_TRACK_AIRPORT = "HGH"
DEFAULT_OUTPUT_PATH = Path("public/special-livery-live.json")
DEFAULT_META_PATH = Path("public/feed-meta.json")
SPECIAL_LIVERIES_PATH = Path("special_liveries.json")
REQUEST_SLEEP_SECONDS = float(os.environ.get("REQUEST_SLEEP_SECONDS", "0.6"))
REQUEST_TIMEOUT_SECONDS = 30
MAX_RECORDS = int(os.environ.get("MAX_RECORDS", "240"))
SCHEDULE_LIMIT = int(os.environ.get("SCHEDULE_LIMIT", "1000"))
CHINA_TZ = timezone(timedelta(hours=8))

AIRPORT_METADATA = {
    "HGH": ("China", "Hangzhou Xiaoshan", 30.24, 120.43),
    "PEK": ("China", "Beijing Capital", 40.08, 116.58),
    "PKX": ("China", "Beijing Daxing", 39.51, 116.41),
    "PVG": ("China", "Shanghai Pudong", 31.14, 121.80),
    "SHA": ("China", "Shanghai Hongqiao", 31.20, 121.34),
    "CAN": ("China", "Guangzhou", 23.39, 113.31),
    "SZX": ("China", "Shenzhen", 22.64, 113.81),
    "CTU": ("China", "Chengdu Shuangliu", 30.58, 103.95),
    "TFU": ("China", "Chengdu Tianfu", 30.32, 104.45),
    "CKG": ("China", "Chongqing", 29.72, 106.64),
    "KMG": ("China", "Kunming", 25.10, 102.93),
    "XIY": ("China", "Xi'an", 34.45, 108.75),
    "WUH": ("China", "Wuhan", 30.78, 114.21),
    "NKG": ("China", "Nanjing", 31.74, 118.86),
    "XMN": ("China", "Xiamen", 24.54, 118.13),
    "CSX": ("China", "Changsha", 28.19, 113.22),
    "TAO": ("China", "Qingdao", 36.36, 120.09),
    "DLC": ("China", "Dalian", 38.97, 121.54),
    "URC": ("China", "Urumqi", 43.91, 87.47),
    "HRB": ("China", "Harbin", 45.62, 126.25),
    "SHE": ("China", "Shenyang", 41.64, 123.48),
    "FOC": ("China", "Fuzhou", 25.93, 119.66),
    "HAK": ("China", "Haikou", 19.93, 110.46),
    "SYX": ("China", "Sanya", 18.30, 109.41),
    "HKG": ("China", "Hong Kong", 22.31, 113.92),
    "MFM": ("China", "Macau", 22.15, 113.59),
    "TPE": ("China", "Taipei Taoyuan", 25.08, 121.23),
    "ICN": ("South Korea", "Seoul Incheon", 37.46, 126.44),
    "NRT": ("Japan", "Tokyo Narita", 35.77, 140.39),
    "HND": ("Japan", "Tokyo Haneda", 35.55, 139.78),
    "KIX": ("Japan", "Osaka Kansai", 34.43, 135.24),
    "BKK": ("Thailand", "Bangkok Suvarnabhumi", 13.69, 100.75),
    "SIN": ("Singapore", "Singapore Changi", 1.36, 103.99),
    "KUL": ("Malaysia", "Kuala Lumpur", 2.75, 101.71),
    "DOH": ("Qatar", "Doha", 25.27, 51.61),
    "DXB": ("United Arab Emirates", "Dubai", 25.25, 55.36),
}

REGISTRATION_KEYS = (
    "reg_number",
    "registration",
    "reg",
    "aircraft_reg",
    "aircraft_registration",
    "aircraft_registration_number",
    "regnum",
)
FLIGHT_KEYS = ("flight_iata", "flight_icao", "flight_number", "flight_no")
AIRLINE_KEYS = ("airline_name", "airline_iata", "airline_icao")
AIRCRAFT_KEYS = ("aircraft_icao", "aircraft_code", "aircraft", "aircraft_model")
DEP_TIME_KEYS = ("dep_time", "dep_time_utc", "dep_estimated", "dep_actual", "dep_time_ts")
ARR_TIME_KEYS = ("arr_time", "arr_time_utc", "arr_estimated", "arr_actual", "arr_time_ts")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def china_today() -> str:
    return datetime.now(CHINA_TZ).date().isoformat()


def normalize_registration(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper().replace(" ", "").replace("_", "-")


def normalize_iata(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().upper()


def pick_first(record: Dict[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return default


def parse_datetime(value: Any, default_tz: timezone = CHINA_TZ) -> Optional[datetime]:
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except (OverflowError, OSError, ValueError):
            return None

    text = str(value).strip()
    if not text:
        return None
    if text.isdigit():
        return parse_datetime(int(text), default_tz)

    normalized = text.replace("T", " ")
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M:%S", "%Y/%m/%d %H:%M"):
        try:
            parsed = datetime.strptime(normalized, fmt)
            return parsed.replace(tzinfo=default_tz)
        except ValueError:
            pass
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_tz)
    return parsed


def iso_or_empty(value: Any) -> str:
    parsed = parse_datetime(value)
    if not parsed:
        return ""
    return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def local_date_key(value: Any) -> Optional[str]:
    parsed = parse_datetime(value)
    if not parsed:
        return None
    return parsed.astimezone(CHINA_TZ).date().isoformat()


def airport_info(code: str) -> Dict[str, Any]:
    normalized = normalize_iata(code)
    meta = AIRPORT_METADATA.get(normalized)
    if not meta:
        return {"code": normalized, "country": "", "name": normalized, "latitude": None, "longitude": None}
    country, name, lat, lon = meta
    return {"code": normalized, "country": country, "name": name, "latitude": lat, "longitude": lon}


def livery_category(livery_name: Any) -> Tuple[str, str]:
    text = str(livery_name or "").strip().lower()
    if "star alliance" in text:
        return "star_alliance", "星空联盟涂装"
    if "skyteam" in text or "sky team" in text:
        return "skyteam", "天合联盟涂装"
    if "oneworld" in text or "one world" in text:
        return "oneworld", "寰宇一家涂装"
    return "other", "其他类型涂装"


def load_special_liveries(path: Path = SPECIAL_LIVERIES_PATH) -> Dict[str, Dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Special livery database not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("special_liveries.json must be a JSON array")

    result: Dict[str, Dict[str, Any]] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        reg = normalize_registration(item.get("registration"))
        if not reg:
            continue
        clean_item = dict(item)
        clean_item["registration"] = reg
        result[reg] = clean_item
    return result


def request_airlabs(api_key: str, params: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    query = dict(params)
    query["api_key"] = api_key
    url = AIRLABS_SCHEDULES_ENDPOINT + "?" + urllib.parse.urlencode(query)
    request = urllib.request.Request(url, headers={"User-Agent": "AeroViewScheduleFeed/1.0"})

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - workflow should report API problems in metadata
        return [], f"request_failed: {type(exc).__name__}: {exc}"

    if isinstance(payload, dict) and payload.get("error"):
        return [], f"api_error: {payload.get('error')}"

    records = payload.get("response") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return [], "invalid_response: missing response array"
    return [record for record in records if isinstance(record, dict)], None


def fetch_hangzhou_schedules(api_key: str, airport: str, schedule_date: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    all_rows: List[Dict[str, Any]] = []
    errors: List[str] = []
    for direction, field in (("arrival", "arr_iata"), ("departure", "dep_iata")):
        params = {field: airport, "limit": SCHEDULE_LIMIT}
        records, error = request_airlabs(api_key, params)
        if error:
            errors.append(f"{field}={airport}: {error}")
        else:
            for record in records:
                enriched = dict(record)
                enriched["_query_direction"] = direction
                all_rows.append(enriched)
        time.sleep(REQUEST_SLEEP_SECONDS)
    return all_rows, errors


def row_direction(schedule: Dict[str, Any], airport: str) -> str:
    explicit = schedule.get("_query_direction")
    if explicit in {"arrival", "departure"}:
        return str(explicit)
    dep = normalize_iata(pick_first(schedule, ["dep_iata", "dep_icao"]))
    arr = normalize_iata(pick_first(schedule, ["arr_iata", "arr_icao"]))
    if arr == airport:
        return "arrival"
    if dep == airport:
        return "departure"
    return "unknown"


def relevant_time(schedule: Dict[str, Any], direction: str) -> Any:
    if direction == "arrival":
        return pick_first(schedule, ARR_TIME_KEYS) or pick_first(schedule, DEP_TIME_KEYS)
    if direction == "departure":
        return pick_first(schedule, DEP_TIME_KEYS) or pick_first(schedule, ARR_TIME_KEYS)
    return pick_first(schedule, ARR_TIME_KEYS) or pick_first(schedule, DEP_TIME_KEYS)


def convert_schedule_record(
    schedule: Dict[str, Any],
    livery: Dict[str, Any],
    airport: str,
    schedule_date: str,
    generated_at: str,
) -> Optional[Dict[str, Any]]:
    direction = row_direction(schedule, airport)
    dep = normalize_iata(pick_first(schedule, ["dep_iata", "dep_icao"]))
    arr = normalize_iata(pick_first(schedule, ["arr_iata", "arr_icao"]))
    if direction == "arrival" and arr != airport:
        return None
    if direction == "departure" and dep != airport:
        return None

    scheduled_raw = relevant_time(schedule, direction)
    scheduled_iso = iso_or_empty(scheduled_raw)
    if scheduled_iso and local_date_key(scheduled_iso) != schedule_date:
        return None

    registration = normalize_registration(pick_first(schedule, REGISTRATION_KEYS))
    if not registration:
        return None

    category, category_label = livery_category(livery.get("livery", ""))
    status = str(pick_first(schedule, ["status"], "scheduled") or "scheduled").strip().lower() or "scheduled"
    flight = str(pick_first(schedule, FLIGHT_KEYS, "UNKNOWN") or "UNKNOWN").upper()

    return {
        "flight": flight,
        "airline": pick_first(schedule, AIRLINE_KEYS, livery.get("airline", "")) or livery.get("airline", ""),
        "aircraft": pick_first(schedule, AIRCRAFT_KEYS, livery.get("aircraft", "")) or livery.get("aircraft", ""),
        "registration": registration,
        "livery": livery.get("livery", "Special Livery"),
        "livery_category": category,
        "livery_category_label": category_label,
        "direction": direction,
        "origin": dep,
        "origin_airport": airport_info(dep),
        "origin_country": airport_info(dep).get("country", ""),
        "destination": arr,
        "destination_airport": airport_info(arr),
        "destination_country": airport_info(arr).get("country", ""),
        "scheduled_departure": iso_or_empty(pick_first(schedule, DEP_TIME_KEYS)),
        "scheduled_arrival": iso_or_empty(pick_first(schedule, ARR_TIME_KEYS)),
        "scheduled_time": scheduled_iso,
        "schedule_date": schedule_date,
        "status": status,
        "updated": generated_at,
        "source": SCHEDULE_SOURCE,
    }


def feed_key(row: Dict[str, Any]) -> str:
    parts = [
        normalize_registration(row.get("registration")),
        str(row.get("flight") or ""),
        str(row.get("direction") or ""),
        str(row.get("origin") or ""),
        str(row.get("destination") or ""),
        str(row.get("scheduled_time") or ""),
    ]
    return "|".join(parts)


def merge_same_day_previous(
    rows: List[Dict[str, Any]],
    previous_rows: List[Dict[str, Any]],
    schedule_date: str,
    generated_at: str,
) -> List[Dict[str, Any]]:
    seen = {feed_key(row) for row in rows}
    merged = list(rows)
    for previous in previous_rows:
        if not isinstance(previous, dict):
            continue
        if previous.get("schedule_date") != schedule_date:
            continue
        if previous.get("source") and previous.get("source") != SCHEDULE_SOURCE:
            continue
        key = feed_key(previous)
        if not key or key in seen:
            continue
        retained = dict(previous)
        retained["retained_from_previous_feed"] = True
        retained["updated"] = generated_at
        seen.add(key)
        merged.append(retained)
    return merged


def build_feed(
    schedules: List[Dict[str, Any]],
    special_liveries: Dict[str, Dict[str, Any]],
    airport: str,
    schedule_date: str,
    previous_rows: Optional[List[Dict[str, Any]]] = None,
    generated_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    generated_at = generated_at or utc_now_iso()
    rows: List[Dict[str, Any]] = []

    for schedule in schedules:
        reg = normalize_registration(pick_first(schedule, REGISTRATION_KEYS))
        if not reg or reg not in special_liveries:
            continue
        row = convert_schedule_record(schedule, special_liveries[reg], airport, schedule_date, generated_at)
        if row:
            rows.append(row)

    deduped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        deduped[feed_key(row)] = row
    rows = list(deduped.values())

    if previous_rows:
        rows = merge_same_day_previous(rows, previous_rows, schedule_date, generated_at)

    rows.sort(key=lambda row: (row.get("scheduled_time") or "9999", row.get("flight") or ""))
    return rows[:MAX_RECORDS]


def demo_feed(schedule_date: str) -> List[Dict[str, Any]]:
    now = utc_now_iso()
    demo_schedules = [
        {
            "_query_direction": "arrival",
            "flight_iata": "CA1703",
            "airline_name": "Air China",
            "aircraft_icao": "B738",
            "reg_number": "B-5497",
            "dep_iata": "PEK",
            "arr_iata": "HGH",
            "dep_time": f"{schedule_date} 08:15",
            "arr_time": f"{schedule_date} 10:25",
            "status": "scheduled",
        },
        {
            "_query_direction": "departure",
            "flight_iata": "MF8070",
            "airline_name": "Xiamen Airlines",
            "aircraft_icao": "B738",
            "reg_number": "B-5633",
            "dep_iata": "HGH",
            "arr_iata": "XMN",
            "dep_time": f"{schedule_date} 13:40",
            "arr_time": f"{schedule_date} 15:20",
            "status": "scheduled",
        },
    ]
    liveries = load_special_liveries()
    return build_feed(demo_schedules, liveries, "HGH", schedule_date, generated_at=now)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def default_previous_feed_url(output_path: Path) -> str:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not repository or "/" not in repository:
        return ""
    owner, repo = repository.split("/", 1)
    return f"https://{owner}.github.io/{repo}/{output_path.name}"


def load_json_array_from_url(url: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "AeroViewScheduleFeed/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return [], None
        return [], f"previous_feed_failed: HTTPError {exc.code}: {exc.reason}"
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

    previous_url = os.environ.get("PREVIOUS_FEED_URL", "").strip() or default_previous_feed_url(output_path)
    if not previous_url:
        return [], None
    return load_json_array_from_url(previous_url)


def main() -> int:
    output_path = Path(os.environ.get("OUTPUT_PATH", str(DEFAULT_OUTPUT_PATH)))
    meta_path = Path(os.environ.get("META_PATH", str(DEFAULT_META_PATH)))
    track_airport = normalize_iata(os.environ.get("TRACK_AIRPORT", DEFAULT_TRACK_AIRPORT)) or DEFAULT_TRACK_AIRPORT
    schedule_date = os.environ.get("SCHEDULE_DATE", "").strip() or china_today()
    generated_at = utc_now_iso()
    errors: List[str] = []
    demo_mode = os.environ.get("DEMO_MODE", "").strip().lower() in {"1", "true", "yes", "on"}

    try:
        special_liveries = load_special_liveries()
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to load special_liveries.json: {exc}", file=sys.stderr)
        return 2

    if demo_mode:
        feed = demo_feed(schedule_date)
    else:
        api_key = os.environ.get("AIRLABS_API_KEY", "").strip()
        if not api_key:
            print("AIRLABS_API_KEY is required unless DEMO_MODE=true", file=sys.stderr)
            return 2
        previous_feed, previous_feed_error = load_previous_feed(output_path)
        if previous_feed_error:
            errors.append(previous_feed_error)
        schedules, fetch_errors = fetch_hangzhou_schedules(api_key, track_airport, schedule_date)
        errors.extend(fetch_errors)
        feed = build_feed(schedules, special_liveries, track_airport, schedule_date, previous_feed, generated_at)

    meta = {
        "generated_at": generated_at,
        "schedule_date": schedule_date,
        "track_airport": track_airport,
        "track_airport_info": airport_info(track_airport),
        "record_count": len(feed),
        "arrival_count": sum(1 for row in feed if row.get("direction") == "arrival"),
        "departure_count": sum(1 for row in feed if row.get("direction") == "departure"),
        "special_livery_count": len(special_liveries),
        "mode": "demo" if demo_mode else "schedule",
        "errors": errors[:50],
        "notes": "Hangzhou schedule scanner. Only schedule rows with an AirLabs-returned aircraft registration can be matched.",
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

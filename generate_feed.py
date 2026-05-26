#!/usr/bin/env python3
"""
AeroView Special Livery Live Feed Generator

This script queries AirLabs Real-Time Flights API for live flights involving
selected airports, cross-matches returned aircraft registration numbers
against special_liveries.json, and writes a static JSON feed for GoDaddy or
any frontend widget to consume.

Required environment variable:
  AIRLABS_API_KEY

Optional environment variables:
  TARGET_AIRPORTS   Comma-separated IATA airport codes.
  TARGET_AIRPORT_PROFILE  global_major or china_all. Default: global_major.
  OUTPUT_PATH       Default: public/special-livery-live.json
  META_PATH         Default: public/feed-meta.json
  DEMO_MODE         If true, writes demo records without calling AirLabs.
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

AIRLABS_ENDPOINT = "https://airlabs.co/api/v9/flights"
GLOBAL_MAJOR_AIRPORTS = [
    "ATL", "LAX", "JFK", "EWR", "ORD", "DFW", "DEN", "SFO", "SEA", "MIA", "IAH", "YYZ",
    "LHR", "CDG", "AMS", "FRA", "IST", "MAD", "BCN", "MUC", "ZRH", "FCO", "VIE", "CPH", "DUB",
    "DXB", "DOH", "AUH", "DEL", "BOM", "SIN", "HKG", "ICN", "NRT", "HND", "BKK", "KUL", "TPE",
    "PVG", "SHA", "PEK", "PKX", "CAN", "SZX", "HGH", "CTU", "TFU",
]
CHINA_ALL_AIRPORTS = [
    "PEK", "PKX", "PVG", "SHA", "CAN", "SZX", "HGH", "CTU", "TFU", "CKG", "KMG", "XIY",
    "WUH", "NKG", "XMN", "CSX", "TAO", "CGO", "HAK", "SYX", "URC", "HRB", "SHE", "DLC",
    "TNA", "FOC", "NNG", "KWE", "LHW", "INC", "HET", "NGB", "WUX", "WNZ", "YTY", "CZX",
    "NTG", "KHN", "HFE", "JJN", "ZUH", "SWA", "NNY", "LYA", "CGQ", "TSN", "SJW", "TYN",
    "LXA", "XNN", "YIH", "ENH", "LJG", "DYG", "KHG", "KRL", "AAT", "KRY", "JHG", "XUZ",
    "WEH", "YNT", "HIA", "HYN", "JUZ", "LZH", "KWL", "BHY", "WUH", "MFM", "HKG", "TPE", "TSA",
]
AIRPORT_PROFILES = {
    "global_major": GLOBAL_MAJOR_AIRPORTS,
    "china_all": CHINA_ALL_AIRPORTS,
}
DEFAULT_TARGET_AIRPORTS = GLOBAL_MAJOR_AIRPORTS
DEFAULT_OUTPUT_PATH = Path("public/special-livery-live.json")
DEFAULT_META_PATH = Path("public/feed-meta.json")
SPECIAL_LIVERIES_PATH = Path("special_liveries.json")
REQUEST_SLEEP_SECONDS = float(os.environ.get("REQUEST_SLEEP_SECONDS", "0.45"))
REQUEST_TIMEOUT_SECONDS = 30
MAX_RECORDS = int(os.environ.get("MAX_RECORDS", "160"))
CHINA_TZ = timezone(timedelta(hours=8))

AIRPORT_METADATA = {
    "ATL": ("United States", "Atlanta", 33.64, -84.43), "LAX": ("United States", "Los Angeles", 33.94, -118.41),
    "JFK": ("United States", "New York JFK", 40.64, -73.78), "EWR": ("United States", "Newark", 40.69, -74.17),
    "ORD": ("United States", "Chicago O'Hare", 41.98, -87.90), "DFW": ("United States", "Dallas/Fort Worth", 32.90, -97.04),
    "DEN": ("United States", "Denver", 39.86, -104.67), "SFO": ("United States", "San Francisco", 37.62, -122.38),
    "SEA": ("United States", "Seattle", 47.45, -122.31), "MIA": ("United States", "Miami", 25.79, -80.29),
    "IAH": ("United States", "Houston", 29.98, -95.34), "YYZ": ("Canada", "Toronto Pearson", 43.68, -79.63),
    "LHR": ("United Kingdom", "London Heathrow", 51.47, -0.45), "CDG": ("France", "Paris Charles de Gaulle", 49.01, 2.55),
    "AMS": ("Netherlands", "Amsterdam", 52.31, 4.76), "FRA": ("Germany", "Frankfurt", 50.04, 8.56),
    "IST": ("Turkey", "Istanbul", 41.28, 28.75), "MAD": ("Spain", "Madrid", 40.47, -3.56),
    "BCN": ("Spain", "Barcelona", 41.30, 2.08), "MUC": ("Germany", "Munich", 48.35, 11.79),
    "ZRH": ("Switzerland", "Zurich", 47.46, 8.55), "FCO": ("Italy", "Rome Fiumicino", 41.80, 12.25),
    "VIE": ("Austria", "Vienna", 48.11, 16.57), "CPH": ("Denmark", "Copenhagen", 55.62, 12.65),
    "DUB": ("Ireland", "Dublin", 53.42, -6.27), "DXB": ("United Arab Emirates", "Dubai", 25.25, 55.36),
    "DOH": ("Qatar", "Doha", 25.27, 51.61), "AUH": ("United Arab Emirates", "Abu Dhabi", 24.43, 54.65),
    "DEL": ("India", "Delhi", 28.56, 77.10), "BOM": ("India", "Mumbai", 19.09, 72.87),
    "SIN": ("Singapore", "Singapore Changi", 1.36, 103.99), "HKG": ("China", "Hong Kong", 22.31, 113.92),
    "ICN": ("South Korea", "Seoul Incheon", 37.46, 126.44), "NRT": ("Japan", "Tokyo Narita", 35.77, 140.39),
    "HND": ("Japan", "Tokyo Haneda", 35.55, 139.78), "BKK": ("Thailand", "Bangkok", 13.69, 100.75),
    "KUL": ("Malaysia", "Kuala Lumpur", 2.75, 101.71), "TPE": ("China", "Taipei Taoyuan", 25.08, 121.23),
    "TSA": ("China", "Taipei Songshan", 25.07, 121.55), "MFM": ("China", "Macau", 22.15, 113.59),
    "PEK": ("China", "Beijing Capital", 40.08, 116.58), "PKX": ("China", "Beijing Daxing", 39.51, 116.41),
    "PVG": ("China", "Shanghai Pudong", 31.14, 121.80), "SHA": ("China", "Shanghai Hongqiao", 31.20, 121.34),
    "CAN": ("China", "Guangzhou", 23.39, 113.31), "SZX": ("China", "Shenzhen", 22.64, 113.81),
    "HGH": ("China", "Hangzhou", 30.24, 120.43), "CTU": ("China", "Chengdu Shuangliu", 30.58, 103.95),
    "TFU": ("China", "Chengdu Tianfu", 30.32, 104.45), "CKG": ("China", "Chongqing", 29.72, 106.64),
    "KMG": ("China", "Kunming", 25.10, 102.93), "XIY": ("China", "Xi'an", 34.45, 108.75),
    "WUH": ("China", "Wuhan", 30.78, 114.21), "NKG": ("China", "Nanjing", 31.74, 118.86),
    "XMN": ("China", "Xiamen", 24.54, 118.13), "CSX": ("China", "Changsha", 28.19, 113.22),
    "TAO": ("China", "Qingdao", 36.36, 120.09), "CGO": ("China", "Zhengzhou", 34.52, 113.84),
    "HAK": ("China", "Haikou", 19.93, 110.46), "SYX": ("China", "Sanya", 18.30, 109.41),
    "URC": ("China", "Urumqi", 43.91, 87.47), "HRB": ("China", "Harbin", 45.62, 126.25),
    "SHE": ("China", "Shenyang", 41.64, 123.48), "DLC": ("China", "Dalian", 38.97, 121.54),
    "TNA": ("China", "Jinan", 36.86, 117.22), "FOC": ("China", "Fuzhou", 25.93, 119.66),
    "NNG": ("China", "Nanning", 22.61, 108.17), "KWE": ("China", "Guiyang", 26.54, 106.80),
    "LHW": ("China", "Lanzhou", 36.52, 103.62), "INC": ("China", "Yinchuan", 38.32, 106.39),
    "HET": ("China", "Hohhot", 40.85, 111.82), "NGB": ("China", "Ningbo", 29.83, 121.46),
    "WUX": ("China", "Wuxi", 31.49, 120.43), "WNZ": ("China", "Wenzhou", 27.91, 120.85),
    "YTY": ("China", "Yangzhou", 32.56, 119.72), "CZX": ("China", "Changzhou", 31.92, 119.78),
    "NTG": ("China", "Nantong", 32.07, 120.98), "KHN": ("China", "Nanchang", 28.86, 115.90),
    "HFE": ("China", "Hefei", 31.78, 117.30), "JJN": ("China", "Quanzhou", 24.80, 118.59),
    "ZUH": ("China", "Zhuhai", 22.01, 113.38), "SWA": ("China", "Jieyang Chaoshan", 23.55, 116.50),
    "NNY": ("China", "Nanyang", 32.98, 112.61), "LYA": ("China", "Luoyang", 34.74, 112.39),
    "CGQ": ("China", "Changchun", 43.99, 125.69), "TSN": ("China", "Tianjin", 39.12, 117.35),
    "SJW": ("China", "Shijiazhuang", 38.28, 114.70), "TYN": ("China", "Taiyuan", 37.75, 112.63),
    "LXA": ("China", "Lhasa", 29.30, 90.91), "XNN": ("China", "Xining", 36.53, 102.04),
    "YIH": ("China", "Yichang", 30.55, 111.48), "ENH": ("China", "Enshi", 30.32, 109.49),
    "LJG": ("China", "Lijiang", 26.68, 100.25), "DYG": ("China", "Zhangjiajie", 29.10, 110.44),
    "KHG": ("China", "Kashgar", 39.54, 76.02), "KRL": ("China", "Korla", 41.70, 86.13),
    "AAT": ("China", "Altay", 47.75, 88.09), "KRY": ("China", "Karamay", 45.47, 84.95),
    "JHG": ("China", "Xishuangbanna", 21.97, 100.76), "XUZ": ("China", "Xuzhou", 34.06, 117.56),
    "WEH": ("China", "Weihai", 37.19, 122.23), "YNT": ("China", "Yantai", 37.40, 121.37),
    "HIA": ("China", "Huai'an", 33.79, 119.13), "HYN": ("China", "Taizhou", 28.56, 121.43),
    "JUZ": ("China", "Quzhou", 28.97, 118.90), "LZH": ("China", "Liuzhou", 24.21, 109.39),
    "KWL": ("China", "Guilin", 25.22, 110.04), "BHY": ("China", "Beihai", 21.54, 109.29),
}


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
        return list(dict.fromkeys(airports))
    profile = os.environ.get("TARGET_AIRPORT_PROFILE", "global_major").strip().lower()
    return list(dict.fromkeys(AIRPORT_PROFILES.get(profile, DEFAULT_TARGET_AIRPORTS)))


def airport_info(code: str) -> Dict[str, Any]:
    normalized = normalize_iata(code)
    meta = AIRPORT_METADATA.get(normalized)
    if not meta:
        return {
            "code": normalized,
            "country": "",
            "name": normalized,
            "latitude": None,
            "longitude": None,
        }
    country, name, lat, lon = meta
    return {
        "code": normalized,
        "country": country,
        "name": name,
        "latitude": lat,
        "longitude": lon,
    }


def livery_category(livery_name: Any) -> Tuple[str, str]:
    text = str(livery_name or "").strip().lower()
    if "star alliance" in text:
        return "star_alliance", "星空联盟涂装"
    if "skyteam" in text or "sky team" in text:
        return "skyteam", "天合联盟涂装"
    if "oneworld" in text or "one world" in text:
        return "oneworld", "寰宇一家涂装"
    return "other", "其他类型涂装"


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
        "livery_category": livery_category(livery.get("livery", ""))[0],
        "livery_category_label": livery_category(livery.get("livery", ""))[1],
        "origin": dep or "",
        "origin_airport": airport_info(dep),
        "origin_country": airport_info(dep).get("country", ""),
        "destination": arr or "",
        "destination_airport": airport_info(arr),
        "destination_country": airport_info(arr).get("country", ""),
        "altitude_m": altitude,
        "speed_kmh": speed,
        "latitude": lat,
        "longitude": lng,
        "status": normalize_status(pick_first(flight, ["status"], "en-route")),
        "updated": updated_iso,
        "source": "AirLabs Real-Time Flights + special_liveries.json",
    }


def feed_key(row: Dict[str, Any]) -> str:
    return normalize_registration(row.get("registration"))


def is_today_record(row: Dict[str, Any], generated_at: str) -> bool:
    today = local_date_key(generated_at)
    return bool(today and local_date_key(row.get("updated")) == today)


def mark_as_landed(row: Dict[str, Any], generated_at: str) -> Dict[str, Any]:
    landed = dict(row)
    landed["status"] = "landed"
    landed["altitude_m"] = 0
    landed["speed_kmh"] = 0
    landed["updated"] = generated_at
    landed["source"] = "Retained from previous feed after leaving live tracking"
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


def latest_rows_by_aircraft(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    latest: Dict[str, Dict[str, Any]] = {}

    for row in rows:
        key = feed_key(row)
        if not key:
            continue
        current = latest.get(key)
        if not current or (row.get("updated") or "") > (current.get("updated") or ""):
            latest[key] = row

    return list(latest.values())


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

    for flight in flights:
        reg = normalize_registration(pick_first(flight, ["reg_number", "registration", "reg"]))
        if not reg or reg not in special_liveries:
            continue
        row = convert_flight_record(flight, special_liveries[reg], target_set, generated_at)
        if not row:
            continue
        rows.append(row)

    rows = latest_rows_by_aircraft(rows)

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


def default_previous_feed_url(output_path: Path) -> str:
    repository = os.environ.get("GITHUB_REPOSITORY", "").strip()
    if not repository or "/" not in repository:
        return ""
    owner, repo = repository.split("/", 1)
    return f"https://{owner}.github.io/{repo}/{output_path.name}"


def load_json_array_from_url(url: str) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    request = urllib.request.Request(url, headers={"User-Agent": "AeroViewLiveFeed/1.0"})
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
    target_airports = get_target_airports()
    target_profile = os.environ.get("TARGET_AIRPORT_PROFILE", "global_major").strip().lower()
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
            print(f"Failed to load previous feed; refusing to publish a shrinking feed: {previous_feed_error}", file=sys.stderr)
            return 3
        flights, fetch_errors = fetch_realtime_flights(api_key, target_airports)
        errors.extend(fetch_errors)
        feed = build_feed(flights, special_liveries, target_airports, previous_feed, generated_at)

    meta = {
        "generated_at": generated_at,
        "target_airports": target_airports,
        "target_airport_profile": target_profile,
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

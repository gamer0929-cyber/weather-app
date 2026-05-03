from flask import Flask, render_template
import requests
import urllib3
from datetime import datetime
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

API_KEY = os.getenv("API_KEY")
LINE_TOKEN = os.getenv("LINE_TOKEN", "")

PINNED_LOCATIONS = ["大園區", "中壢區"]

PERIODS = [
    ("06-11", 6, 11),
    ("11-14", 11, 14),
    ("14-17", 14, 17),
    ("17-24", 17, 24)
]

URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-093"


def normalize_name(name):
    if not name:
        return ""
    return str(name).replace("臺", "台").strip()


def fetch_weather():
    if not API_KEY:
        return {
            "success": "false",
            "message": "API_KEY 未設定"
        }

    params = {
        "Authorization": API_KEY,
        "format": "JSON",
        "locationName": ",".join(PINNED_LOCATIONS)
    }

    try:
        response = requests.get(
            URL,
            params=params,
            timeout=30,
            verify=False
        )

        try:
            return response.json()
        except Exception:
            return {
                "success": "false",
                "message": "CWA 回傳不是 JSON"
            }

    except Exception as e:
        return {
            "success": "false",
            "message": f"API讀取失敗：{e}"
        }


def get_locations(data):
    records = data.get("records", {})

    groups = records.get("locations") or records.get("Locations") or []

    all_locations = []

    if groups:
        for group in groups:
            items = group.get("location") or group.get("Location") or []
            all_locations.extend(items)

    direct_locations = records.get("location") or records.get("Location") or []
    all_locations.extend(direct_locations)

    return all_locations


def get_name(loc):
    return (
        loc.get("locationName")
        or loc.get("LocationName")
        or loc.get("townName")
        or loc.get("TownName")
        or ""
    )


def get_elements(loc):
    return loc.get("weatherElement") or loc.get("WeatherElement") or []


def get_element_name(element):
    return element.get("elementName") or element.get("ElementName") or ""


def get_times(element):
    return element.get("time") or element.get("Time") or []


def parse_time(text):
    if not text:
        return None

    text = str(text).replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(text)
    except Exception:
        try:
            return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except Exception:
            return None


def get_start(t):
    return (
        t.get("startTime")
        or t.get("StartTime")
        or t.get("dataTime")
        or t.get("DataTime")
    )


def get_end(t):
    return (
        t.get("endTime")
        or t.get("EndTime")
        or get_start(t)
    )


def overlaps(t, period_start, period_end):
    start_dt = parse_time(get_start(t))
    end_dt = parse_time(get_end(t))

    if not start_dt:
        return False

    start_hour = start_dt.hour

    if end_dt:
        end_hour = end_dt.hour

        if end_dt.date() > start_dt.date():
            end_hour = 24

        return start_hour < period_end and end_hour > period_start

    return period_start <= start_hour < period_end


def extract_value(t):
    values = t.get("elementValue") or t.get("ElementValue") or []

    if not values:
        return None

    value_obj = values[0]

    keys = [
        "value",
        "Value",
        "ProbabilityOfPrecipitation",
        "Temperature",
        "MinTemperature",
        "MaxTemperature"
    ]

    for key in keys:
        if key in value_obj:
            raw = value_obj.get(key)

            try:
                return int(float(raw))
            except Exception:
                return None

    return None


def parse_weather(data):
    if data.get("success") == "false":
        return [{
            "location": "資料讀取失敗",
            "period": data.get("message", "API錯誤"),
            "rain": "-",
            "min_temp": "-",
            "max_temp": "-"
        }]

    results = []
    targets = [normalize_name(x) for x in PINNED_LOCATIONS]
    locations = get_locations(data)

    if not locations:
        return [{
            "location": "資料讀取失敗",
            "period": "API無資料",
            "rain": "-",
            "min_temp": "-",
            "max_temp": "-"
        }]

    for loc in locations:
        name = normalize_name(get_name(loc))

        if name not in targets:
            continue

        element_map = {}

        for element in get_elements(loc):
            element_name = get_element_name(element)
            element_map[element_name] = get_times(element)

        rain_data = (
            element_map.get("PoP12h")
            or element_map.get("PoP6h")
            or element_map.get("PoP3h")
            or element_map.get("PoP")
            or []
        )

        min_temp_data = (
            element_map.get("MinT")
            or element_map.get("T")
            or []
        )

        max_temp_data = (
            element_map.get("MaxT")
            or element_map.get("T")
            or []
        )

        for label, period_start, period_end in PERIODS:
            rain_probs = []
            min_temps = []
            max_temps = []

            for t in rain_data:
                if overlaps(t, period_start, period_end):
                    value = extract_value(t)
                    if value is not None:
                        rain_probs.append(value)

            for t in min_temp_data:
                if overlaps(t, period_start, period_end):
                    value = extract_value(t)
                    if value is not None:
                        min_temps.append(value)

            for t in max_temp_data:
                if overlaps(t, period_start, period_end):
                    value = extract_value(t)
                    if value is not None:
                        max_temps.append(value)

            results.append({
                "location": name,
                "period": label,
                "rain": max(rain_probs) if rain_probs else "-",
                "min_temp": min(min_temps) if min_temps else "-",
                "max_temp": max(max_temps) if max_temps else "-"
            })

    if not results:
        return [{
            "location": "找不到釘選地區",
            "period": "大園區 / 中壢區",
            "rain": "-",
            "min_temp": "-",
            "max_temp": "-"
        }]

    return results


@app.route("/")
def index():
    data = fetch_weather()
    weather = parse_weather(data)

    return render_template(
        "index.html",
        weather=weather
    )


@app.route("/debug")
def debug():
    return fetch_weather()


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )

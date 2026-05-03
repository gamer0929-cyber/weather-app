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

# 桃園市未來2天天氣預報
URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-005"


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
            data = response.json()
        except Exception:
            return {
                "success": "false",
                "message": "CWA 回傳不是 JSON",
                "status_code": response.status_code,
                "text": response.text[:300]
            }

        if response.status_code != 200:
            data["http_status"] = response.status_code

        return data

    except Exception as e:
        return {
            "success": "false",
            "message": f"API讀取失敗：{e}"
        }


def get_records_locations(data):
    records = data.get("records", {})

    groups = records.get("locations") or records.get("Locations") or []

    if groups:
        all_locations = []

        for group in groups:
            locations = (
                group.get("location")
                or group.get("Location")
                or []
            )
            all_locations.extend(locations)

        return all_locations

    return records.get("location") or records.get("Location") or []


def get_location_name(loc):
    return (
        loc.get("locationName")
        or loc.get("LocationName")
        or loc.get("location")
        or loc.get("Location")
        or "未知地區"
    )


def get_weather_elements(loc):
    return (
        loc.get("weatherElement")
        or loc.get("WeatherElement")
        or []
    )


def get_element_name(element):
    return (
        element.get("elementName")
        or element.get("ElementName")
        or ""
    )


def get_element_times(element):
    return (
        element.get("time")
        or element.get("Time")
        or []
    )


def get_start_time(time_item):
    return (
        time_item.get("startTime")
        or time_item.get("StartTime")
        or time_item.get("dataTime")
        or time_item.get("DataTime")
    )


def get_end_time(time_item):
    return (
        time_item.get("endTime")
        or time_item.get("EndTime")
        or get_start_time(time_item)
    )


def parse_time(time_text):
    if not time_text:
        return None

    text = str(time_text).replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(text)
    except Exception:
        pass

    try:
        return datetime.strptime(str(time_text)[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def get_value(time_item):
    values = (
        time_item.get("elementValue")
        or time_item.get("ElementValue")
        or []
    )

    if not values:
        return None

    value_obj = values[0]

    possible_keys = [
        "value",
        "Value",
        "ProbabilityOfPrecipitation",
        "Temperature",
        "MinTemperature",
        "MaxTemperature",
        "Weather",
        "WeatherDescription"
    ]

    for key in possible_keys:
        if key in value_obj:
            raw = value_obj.get(key)

            if raw in [None, ""]:
                return None

            try:
                return int(raw)
            except Exception:
                return raw

    return None


def time_overlaps_period(time_item, period_start_hour, period_end_hour):
    start_text = get_start_time(time_item)
    end_text = get_end_time(time_item)

    start_dt = parse_time(start_text)
    end_dt = parse_time(end_text)

    if not start_dt:
        return False

    start_hour = start_dt.hour

    if end_dt:
        end_hour = end_dt.hour

        if end_dt.date() > start_dt.date():
            end_hour = 24

        return start_hour < period_end_hour and end_hour > period_start_hour

    return period_start_hour <= start_hour < period_end_hour


def parse_weather(data):
    results = []

    if data.get("success") == "false":
        return [{
            "location": "資料讀取失敗",
            "period": data.get("message", "API錯誤"),
            "rain": "-",
            "min_temp": "-",
            "max_temp": "-"
        }]

    locations = get_records_locations(data)

    if not locations:
        return [{
            "location": "資料讀取失敗",
            "period": "API無資料",
            "rain": "-",
            "min_temp": "-",
            "max_temp": "-"
        }]

    target_locations = [normalize_name(x) for x in PINNED_LOCATIONS]

    for loc in locations:
        name = get_location_name(loc)
        normalized_name = normalize_name(name)

        if normalized_name not in target_locations:
            continue

        elements = {}

        for element in get_weather_elements(loc):
            element_name = get_element_name(element)
            element_times = get_element_times(element)
            elements[element_name] = element_times

        pop_data = (
            elements.get("PoP12h")
            or elements.get("PoP6h")
            or elements.get("PoP3h")
            or elements.get("PoP")
            or []
        )

        min_temp_data = (
            elements.get("MinT")
            or elements.get("MinAT")
            or elements.get("T")
            or []
        )

        max_temp_data = (
            elements.get("MaxT")
            or elements.get("MaxAT")
            or elements.get("T")
            or []
        )

        for label, period_start, period_end in PERIODS:
            rain_probs = []
            min_temps = []
            max_temps = []

            for t in pop_data:
                if time_overlaps_period(t, period_start, period_end):
                    value = get_value(t)
                    if isinstance(value, int):
                        rain_probs.append(value)

            for t in min_temp_data:
                if time_overlaps_period(t, period_start, period_end):
                    value = get_value(t)
                    if isinstance(value, int):
                        min_temps.append(value)

            for t in max_temp_data:
                if time_overlaps_period(t, period_start, period_end):
                    value = get_value(t)
                    if isinstance(value, int):
                        max_temps.append(value)

            rain = max(rain_probs) if rain_probs else "-"
            min_temp = min(min_temps) if min_temps else "-"
            max_temp = max(max_temps) if max_temps else "-"

            results.append({
                "location": name,
                "period": label,
                "rain": rain,
                "min_temp": min_temp,
                "max_temp": max_temp
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
    data = fetch_weather()
    return data


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )

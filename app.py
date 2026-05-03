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
        "format": "JSON"
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
            return {
                "success": "false",
                "message": f"HTTP {response.status_code}",
                "data": data
            }

        return data

    except Exception as e:
        return {
            "success": "false",
            "message": f"API讀取失敗：{e}"
        }


def get_first_value(obj):
    if obj is None:
        return None

    if isinstance(obj, (int, float)):
        return int(obj)

    if isinstance(obj, str):
        text = obj.strip()
        if text == "":
            return None
        try:
            return int(float(text))
        except Exception:
            return text

    if isinstance(obj, list):
        for item in obj:
            value = get_first_value(item)
            if value is not None:
                return value
        return None

    if isinstance(obj, dict):
        priority_keys = [
            "value",
            "Value",
            "Temperature",
            "MinTemperature",
            "MaxTemperature",
            "ProbabilityOfPrecipitation",
            "Weather",
            "WeatherDescription"
        ]

        for key in priority_keys:
            if key in obj:
                value = get_first_value(obj.get(key))
                if value is not None:
                    return value

        for value in obj.values():
            found = get_first_value(value)
            if found is not None:
                return found

    return None


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


def time_overlaps_period(time_item, period_start_hour, period_end_hour, target_date):
    start_text = get_start_time(time_item)
    end_text = get_end_time(time_item)

    start_dt = parse_time(start_text)
    end_dt = parse_time(end_text)

    if not start_dt:
        return False

    if start_dt.date() != target_date:
        return False

    start_hour = start_dt.hour

    if end_dt:
        end_hour = end_dt.hour

        if end_dt.date() > start_dt.date():
            end_hour = 24

        return start_hour < period_end_hour and end_hour > period_start_hour

    return period_start_hour <= start_hour < period_end_hour


def get_location_name(loc):
    return (
        loc.get("locationName")
        or loc.get("LocationName")
        or loc.get("townName")
        or loc.get("TownName")
        or loc.get("name")
        or loc.get("Name")
        or ""
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


def collect_target_locations(obj, target_names):
    found = []

    if isinstance(obj, dict):
        name = normalize_name(get_location_name(obj))
        elements = get_weather_elements(obj)

        if name in target_names and elements:
            found.append(obj)

        for value in obj.values():
            found.extend(collect_target_locations(value, target_names))

    elif isinstance(obj, list):
        for item in obj:
            found.extend(collect_target_locations(item, target_names))

    return found


def pick_target_date(elements):
    dates = []

    for times in elements.values():
        for t in times:
            dt = parse_time(get_start_time(t))
            if dt:
                dates.append(dt.date())

    if not dates:
        return None

    return min(dates)


def is_rain_element(name):
    n = str(name)
    return (
        "PoP" in n
        or "降雨機率" in n
        or "降雨" in n
    )


def is_min_temp_element(name):
    n = str(name)
    return (
        n == "MinT"
        or "最低溫" in n
        or "最低溫度" in n
        or "MinTemperature" in n
    )


def is_max_temp_element(name):
    n = str(name)
    return (
        n == "MaxT"
        or "最高溫" in n
        or "最高溫度" in n
        or "MaxTemperature" in n
    )


def is_temp_element(name):
    n = str(name)
    return (
        n == "T"
        or n == "溫度"
        or "Temperature" in n
    )


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

    target_names = [normalize_name(x) for x in PINNED_LOCATIONS]
    locations = collect_target_locations(data, target_names)

    if not locations:
        return [{
            "location": "找不到釘選地區",
            "period": "大園區 / 中壢區",
            "rain": "-",
            "min_temp": "-",
            "max_temp": "-"
        }]

    for loc in locations:
        name = normalize_name(get_location_name(loc))

        elements = {}

        for element in get_weather_elements(loc):
            element_name = get_element_name(element)
            element_times = get_element_times(element)

            if element_name and element_times:
                elements[element_name] = element_times

        target_date = pick_target_date(elements)

        if not target_date:
            continue

        rain_sources = []
        min_temp_sources = []
        max_temp_sources = []
        temp_sources = []

        for element_name, times in elements.items():
            if is_rain_element(element_name):
                rain_sources.extend(times)

            if is_min_temp_element(element_name):
                min_temp_sources.extend(times)

            if is_max_temp_element(element_name):
                max_temp_sources.extend(times)

            if is_temp_element(element_name):
                temp_sources.extend(times)

        if not min_temp_sources:
            min_temp_sources = temp_sources

        if not max_temp_sources:
            max_temp_sources = temp_sources

        for label, period_start, period_end in PERIODS:
            rain_probs = []
            min_temps = []
            max_temps = []

            for t in rain_sources:
                if time_overlaps_period(t, period_start, period_end, target_date):
                    value = get_first_value(
                        t.get("elementValue")
                        or t.get("ElementValue")
                        or t
                    )
                    if isinstance(value, int):
                        rain_probs.append(value)

            for t in min_temp_sources:
                if time_overlaps_period(t, period_start, period_end, target_date):
                    value = get_first_value(
                        t.get("elementValue")
                        or t.get("ElementValue")
                        or t
                    )
                    if isinstance(value, int):
                        min_temps.append(value)

            for t in max_temp_sources:
                if time_overlaps_period(t, period_start, period_end, target_date):
                    value = get_first_value(
                        t.get("elementValue")
                        or t.get("ElementValue")
                        or t
                    )
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
            "location": "資料讀取失敗",
            "period": "有找到地區，但沒有時段資料",
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

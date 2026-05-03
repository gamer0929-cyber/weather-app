from flask import Flask, render_template
import requests
import urllib3
from datetime import datetime
import os

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

API_KEY = os.getenv("API_KEY")
LINE_TOKEN = os.getenv("LINE_TOKEN", "")

LOCATIONS = ["大園區", "中壢區"]

PERIODS = [
    ("06-11", 6, 11),
    ("11-14", 11, 14),
    ("14-17", 14, 17),
    ("17-24", 17, 24)
]

URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-061"


def fetch_weather():
    params = {
        "Authorization": API_KEY,
        "format": "JSON",
        "locationName": ",".join(LOCATIONS)
    }

    response = requests.get(URL, params=params, verify=False, timeout=15)
    return response.json()


def safe_value(item):
    try:
        return int(item["elementValue"][0]["value"])
    except Exception:
        return None


def parse_weather(data):
    results = []

    records = data.get("records", {})
    locations_block = records.get("locations", [])

    # 如果 API 回傳不是我們要的格式，顯示錯誤，不讓網站掛掉
    if not locations_block:
        return [{
            "location": "資料讀取失敗",
            "period": "請檢查 API",
            "rain": "API格式不同",
            "min_temp": "-",
            "max_temp": "-"
        }]

    for loc in locations_block[0].get("location", []):
        name = loc.get("locationName", "未知地區")
        elements = {
            e.get("elementName"): e.get("time", [])
            for e in loc.get("weatherElement", [])
        }

        pop_data = elements.get("PoP12h", [])
        min_temp_data = elements.get("MinT", [])
        max_temp_data = elements.get("MaxT", [])

        for label, start, end in PERIODS:
            rain_probs = []
            min_temps = []
            max_temps = []

            for t in pop_data:
                hour = datetime.fromisoformat(t["startTime"]).hour
                if start <= hour < end:
                    value = safe_value(t)
                    if value is not None:
                        rain_probs.append(value)

            for t in min_temp_data:
                hour = datetime.fromisoformat(t["startTime"]).hour
                if start <= hour < end:
                    value = safe_value(t)
                    if value is not None:
                        min_temps.append(value)

            for t in max_temp_data:
                hour = datetime.fromisoformat(t["startTime"]).hour
                if start <= hour < end:
                    value = safe_value(t)
                    if value is not None:
                        max_temps.append(value)

            if rain_probs:
                rain = max(rain_probs)
                min_temp = min(min_temps) if min_temps else "-"
                max_temp = max(max_temps) if max_temps else "-"

                results.append({
                    "location": name,
                    "period": label,
                    "rain": rain,
                    "min_temp": min_temp,
                    "max_temp": max_temp
                })

    return results


@app.route("/")
def index():
    data = fetch_weather()
    weather = parse_weather(data)
    return render_template("index.html", weather=weather)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

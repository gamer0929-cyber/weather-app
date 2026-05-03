from flask import Flask, render_template
import requests
from datetime import datetime
import os

app = Flask(__name__)

API_KEY = os.getenv("API_KEY")
LINE_TOKEN = os.getenv("LINE_TOKEN", "")

# 只顯示你釘選的區域
LOCATIONS = ["大園區", "中壢區"]

PERIODS = [
    ("06-11", 6, 11),
    ("11-14", 11, 14),
    ("14-17", 14, 17),
    ("17-24", 17, 24)
]

# 改用全台鄉鎮市區資料集
URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-093"


def fetch_weather():
    params = {
        "Authorization": API_KEY,
        "format": "JSON",
        "locationName": ",".join(LOCATIONS)
    }

    try:
        response = requests.get(URL, params=params, timeout=30, verify=False)
        return response.json()
    except Exception as e:
        print("API讀取失敗:", e)
        return {}


def parse_weather(data):
    results = []

    try:
        locations = data["records"]["locations"][0]["location"]
    except KeyError:
        return results

    for loc in locations:
        name = (
            loc.get("locationName")
            or loc.get("LocationName")
            or "未知地區"
        )

        # 非釘選區域直接跳過
        if name not in LOCATIONS:
            continue

        elements = {}

        for e in loc["weatherElement"]:
            elements[e["elementName"]] = e["time"]

        for label, start, end in PERIODS:
            rain_probs = []
            temps = []

            # 降雨機率
            if "PoP12h" in elements:
                for t in elements["PoP12h"]:
                    try:
                        hour = datetime.fromisoformat(
                            t["startTime"].replace("Z", "")
                        ).hour

                        if start <= hour < end:
                            val = t["elementValue"][0]["value"]
                            if val and val != "":
                                rain_probs.append(int(val))
                    except:
                        continue

            # 最低溫
            if "MinT" in elements:
                for t in elements["MinT"]:
                    try:
                        hour = datetime.fromisoformat(
                            t["startTime"].replace("Z", "")
                        ).hour

                        if start <= hour < end:
                            val = t["elementValue"][0]["value"]
                            if val and val != "":
                                temps.append(int(val))
                    except:
                        continue

            if rain_probs or temps:
                rain = max(rain_probs) if rain_probs else "-"
                min_temp = min(temps) if temps else "-"
                max_temp = max(temps) if temps else "-"

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

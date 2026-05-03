from flask import Flask, render_template
import requests
from datetime import datetime
import os
import urllib3

# 關閉 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

API_KEY = os.getenv("API_KEY")
LINE_TOKEN = os.getenv("LINE_TOKEN", "")

# 你釘選的區域
LOCATIONS = ["大園區", "中壢區"]

PERIODS = [
    ("06-11", 6, 11),
    ("11-14", 11, 14),
    ("14-17", 14, 17),
    ("17-24", 17, 24)
]

# 桃園市資料集
URL = "https://opendata.cwa.gov.tw/api/v1/rest/datastore/F-D0047-005"


def fetch_weather():
    params = {
        "Authorization": API_KEY,
        "format": "JSON",
        "locationName": ",".join(LOCATIONS)
    }

    try:
        response = requests.get(
            URL,
            params=params,
            timeout=30,
            verify=False
        )

        data = response.json()

        if "records" not in data:
            print("API錯誤:", data)

        return data

    except Exception as e:
        print("API讀取失敗:", e)
        return {}


def safe_int(value):
    try:
        return int(value)
    except:
        return None


def parse_weather(data):
    results = []

    try:
        locations = data["records"]["locations"][0]["location"]
    except:
        return results

    for loc in locations:
        name = loc.get("locationName", "未知地區")

        # 只保留釘選區
        if name not in LOCATIONS:
            continue

        weather_elements = {}

        for e in loc["weatherElement"]:
            weather_elements[e["elementName"]] = e["time"]

        for label, start, end in PERIODS:
            rain_probs = []
            temps = []

            # 降雨率
            if "PoP12h" in weather_elements:
                for t in weather_elements["PoP12h"]:
                    try:
                        hour = datetime.fromisoformat(
                            t["startTime"].replace("Z", "")
                        ).hour

                        if start <= hour < end:
                            val = safe_int(
                                t["elementValue"][0]["value"]
                            )
                            if val is not None:
                                rain_probs.append(val)
                    except:
                        continue

            # 最低溫
            if "MinT" in weather_elements:
                for t in weather_elements["MinT"]:
                    try:
                        hour = datetime.fromisoformat(
                            t["startTime"].replace("Z", "")
                        ).hour

                        if start <= hour < end:
                            val = safe_int(
                                t["elementValue"][0]["value"]
                            )
                            if val is not None:
                                temps.append(val)
                    except:
                        continue

            # 若沒資料則顯示預設值
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

    return render_template(
        "index.html",
        weather=weather
    )


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )

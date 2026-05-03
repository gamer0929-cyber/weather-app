from flask import Flask, render_template
import requests
from datetime import datetime
import os

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
    return requests.get(URL, params=params).json()


def parse_weather(data):
    results = []

    for loc in data['records']['locations'][0]['location']:
        name = loc['locationName']
        elements = {e['elementName']: e['time'] for e in loc['weatherElement']}

        for label, start, end in PERIODS:
            rain_probs = []
            temps = []

            for t in elements['PoP12h']:
                hour = datetime.fromisoformat(t['startTime']).hour
                if start <= hour < end:
                    rain_probs.append(int(t['elementValue'][0]['value']))

            for t in elements['MinT']:
                hour = datetime.fromisoformat(t['startTime']).hour
                if start <= hour < end:
                    temps.append(int(t['elementValue'][0]['value']))

            if rain_probs:
                rain = max(rain_probs)
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

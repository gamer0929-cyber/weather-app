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

    response = requests.get(
        URL,
        params=params,
        verify=False,
        timeout=15
    )

    return response.json()


def get_value(time_item):
    values = time_item.get("elementValue") or time_item.get("ElementValue") or []

    if not values:
        return None

    value_obj = values[0]

    for key in [
        "value",
        "Value",
        "Temperature",
        "ProbabilityOfPrecipitation"
    ]:
        if key in value_obj:
            try:
                return int(value_obj[key])
            except:
                return value_obj[key]

    return None


def get_start_time(time_item):
    return (
        time_item.get("startTime")
        or time_item.get("StartTime")
        or time_item.get("dataTime")
        or time_item.get("DataTime")
    )


def parse_weather(data):
    results = []

    records = data.get("records", {})

    locations_groups = (
        records.get("locations")
        or records.get("Locations")
        or []
    )

    if locations_groups:
        locations = (
            locations_groups[0].get("location")
            or locations_groups[0].get("Location")
            or []
        )
    else:
        locations = records.get("location") or records.get("Location") or []

    if not locations:
        return [{
            "location": "資料讀取失敗",
            "period": "API格式不同",
            "rain": "-",
            "min_temp": "-",
            "max_temp": "-"
        }]

    for loc in locations:
        name = (
            loc.get("locationName")
            or loc.get("LocationName")
            or "未知地區"
        )

        weather_elements = (
            loc.get("weatherElement")
            or loc.get("WeatherElement")
            or []
        )

        elements = {}

        for e in weather_elements:
            element_name = e.get("elementName") or e.get("ElementName")
            times = e.get("time") or e.get("Time") or []
            elements[element_name] = times

        pop_data = elements.get("PoP12h") or elements.get("PoP6h") or elements.get("PoP") or []
        min_temp_data = elements.get("MinT") or []
        max_temp_data = elements.get("MaxT") or []

        for label, start, end in PERIODS:
            rain_probs = []
            min_temps = []
            max_temps = []

            for t in pop_data:
                start_time = get_start_time(t)
                if not start_time:
                    continue

                hour = datetime.fromisoformat(start_time).hour

                if start <= hour < end:
                    value = get_value(t)
                    if isinstance(value, int):
                        rain_probs.append(value)

            for t in min_temp_data:
                start_time = get_start_time(t)
                if not start_time:
                    continue

                hour = datetime.fromisoformat(start_time).hour

                if start <= hour < end:
                    value = get_value(t)
                    if isinstance(value, int):
                        min_temps.append(value)

            for t in max_temp_data:
                start_time = get_start_time(t)
                if not start_time:
                    continue

                hour = datetime.fromisoformat(start_time).hour

                if start <= hour < end:
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

    return results


@app.route("/")
def index():
    data = fetch_weather()
    weather = parse_weather(data)
    return render_template("index.html", weather=weather)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

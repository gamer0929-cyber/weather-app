from flask import Flask, render_template
import requests
import urllib3
from datetime import datetime
import xml.etree.ElementTree as ET

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

app = Flask(__name__)

# 只顯示你釘選的地區
PINNED_LOCATIONS = ["大園區", "中壢區"]

# 你指定的時段
PERIODS = [
    ("06-11", 6, 11),
    ("11-14", 11, 14),
    ("14-17", 14, 17),
    ("17-24", 17, 24)
]

# 桃園市鄉鎮預報 XML
URL = "https://cwaopendata.s3.ap-northeast-1.amazonaws.com/Forecast/F-D0047-007.xml"


def clean_tag(tag):
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def is_tag(element, tag_name):
    return clean_tag(element.tag).lower() == tag_name.lower()


def normalize_name(name):
    if not name:
        return ""
    return str(name).replace("臺", "台").strip()


def get_text_direct(element, tag_names):
    if isinstance(tag_names, str):
        tag_names = [tag_names]

    for child in list(element):
        for tag_name in tag_names:
            if is_tag(child, tag_name):
                return (child.text or "").strip()

    return ""


def get_text_deep(element, tag_names):
    if isinstance(tag_names, str):
        tag_names = [tag_names]

    for child in element.iter():
        for tag_name in tag_names:
            if is_tag(child, tag_name):
                return (child.text or "").strip()

    return ""


def fetch_xml_root():
    try:
        response = requests.get(URL, timeout=30, verify=False)
        response.raise_for_status()
        return ET.fromstring(response.content)

    except Exception as e:
        print("XML讀取失敗：", e)
        return None


def parse_time(text):
    if not text:
        return None

    text = str(text).replace("Z", "+00:00")

    try:
        return datetime.fromisoformat(text)
    except Exception:
        pass

    try:
        return datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


def get_location_name(location):
    return get_text_direct(
        location,
        ["LocationName", "locationName"]
    )


def get_weather_elements(location):
    result = []

    for child in list(location):
        if is_tag(child, "WeatherElement") or is_tag(child, "weatherElement"):
            result.append(child)

    return result


def get_element_name(weather_element):
    return get_text_direct(
        weather_element,
        ["ElementName", "elementName"]
    )


def get_times(weather_element):
    result = []

    for child in list(weather_element):
        if is_tag(child, "Time") or is_tag(child, "time"):
            result.append(child)

    return result


def get_start_time(time_item):
    return get_text_direct(
        time_item,
        ["StartTime", "startTime", "DataTime", "dataTime"]
    )


def get_end_time(time_item):
    end_text = get_text_direct(
        time_item,
        ["EndTime", "endTime"]
    )

    if end_text:
        return end_text

    return get_start_time(time_item)


def extract_number(time_item):
    possible_tags = [
        "Value",
        "value",
        "ProbabilityOfPrecipitation",
        "Temperature",
        "MinTemperature",
        "MaxTemperature",
        "DewPoint"
    ]

    for tag in possible_tags:
        text = get_text_deep(time_item, tag)

        if text:
            try:
                return int(float(text))
            except Exception:
                continue

    # 備用：直接掃所有文字，抓第一個數字
    for child in time_item.iter():
        text = (child.text or "").strip()

        if text:
            try:
                return int(float(text))
            except Exception:
                continue

    return None


def collect_locations(root):
    locations = []

    if root is None:
        return locations

    for element in root.iter():
        if is_tag(element, "Location") or is_tag(element, "location"):
            name = get_location_name(element)

            if name:
                locations.append(element)

    return locations


def pick_target_date(element_map):
    dates = []

    for times in element_map.values():
        for time_item in times:
            dt = parse_time(get_start_time(time_item))

            if dt:
                dates.append(dt.date())

    if not dates:
        return None

    return min(dates)


def time_overlaps_period(time_item, period_start_hour, period_end_hour, target_date):
    start_dt = parse_time(get_start_time(time_item))
    end_dt = parse_time(get_end_time(time_item))

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


def is_rain_element(element_name):
    name = str(element_name)

    return (
        "PoP" in name
        or "降雨機率" in name
        or "降雨" in name
        or "降水" in name
    )


def is_min_temp_element(element_name):
    name = str(element_name)

    return (
        name == "MinT"
        or "最低溫" in name
        or "最低溫度" in name
        or "MinTemperature" in name
    )


def is_max_temp_element(element_name):
    name = str(element_name)

    return (
        name == "MaxT"
        or "最高溫" in name
        or "最高溫度" in name
        or "MaxTemperature" in name
    )


def is_temp_element(element_name):
    name = str(element_name)

    return (
        name == "T"
        or name == "溫度"
        or "Temperature" in name
        or "平均溫度" in name
    )


def rain_scope_text(rain):
    if rain == "-":
        return "資料不足"

    try:
        rain = int(rain)
    except Exception:
        return "資料不足"

    if rain >= 70:
        return "範圍偏廣"
    elif rain >= 40:
        return "局部降雨"
    elif rain >= 20:
        return "零星降雨"
    else:
        return "降雨機率低"


def parse_weather(root):
    if root is None:
        return [{
            "location": "資料讀取失敗",
            "period": "XML無法讀取",
            "rain": "-",
            "min_temp": "-",
            "max_temp": "-",
            "scope": "資料不足"
        }]

    results = []
    target_names = [normalize_name(x) for x in PINNED_LOCATIONS]
    all_locations = collect_locations(root)

    # 依照你釘選順序顯示：大園區 → 中壢區
    for target_name in target_names:
        target_location = None

        for location in all_locations:
            name = normalize_name(get_location_name(location))

            if name == target_name:
                target_location = location
                break

        if target_location is None:
            results.append({
                "location": target_name,
                "period": "找不到此地區",
                "rain": "-",
                "min_temp": "-",
                "max_temp": "-",
                "scope": "資料不足"
            })
            continue

        element_map = {}

        for weather_element in get_weather_elements(target_location):
            element_name = get_element_name(weather_element)
            times = get_times(weather_element)

            if element_name and times:
                element_map[element_name] = times

        target_date = pick_target_date(element_map)

        if not target_date:
            results.append({
                "location": target_name,
                "period": "沒有時間資料",
                "rain": "-",
                "min_temp": "-",
                "max_temp": "-",
                "scope": "資料不足"
            })
            continue

        rain_data = []
        min_temp_data = []
        max_temp_data = []
        backup_temp_data = []

        for element_name, times in element_map.items():
            if is_rain_element(element_name):
                rain_data.extend(times)

            if is_min_temp_element(element_name):
                min_temp_data.extend(times)

            if is_max_temp_element(element_name):
                max_temp_data.extend(times)

            if is_temp_element(element_name):
                backup_temp_data.extend(times)

        # 如果 XML 沒有 MinT / MaxT，就用 T 當備援
        if not min_temp_data:
            min_temp_data = backup_temp_data

        if not max_temp_data:
            max_temp_data = backup_temp_data

        for label, period_start, period_end in PERIODS:
            rain_probs = []
            min_temps = []
            max_temps = []

            for time_item in rain_data:
                if time_overlaps_period(
                    time_item,
                    period_start,
                    period_end,
                    target_date
                ):
                    value = extract_number(time_item)

                    if value is not None:
                        rain_probs.append(value)

            for time_item in min_temp_data:
                if time_overlaps_period(
                    time_item,
                    period_start,
                    period_end,
                    target_date
                ):
                    value = extract_number(time_item)

                    if value is not None:
                        min_temps.append(value)

            for time_item in max_temp_data:
                if time_overlaps_period(
                    time_item,
                    period_start,
                    period_end,
                    target_date
                ):
                    value = extract_number(time_item)

                    if value is not None:
                        max_temps.append(value)

            rain = max(rain_probs) if rain_probs else "-"
            min_temp = min(min_temps) if min_temps else "-"
            max_temp = max(max_temps) if max_temps else "-"

            results.append({
                "location": target_name,
                "period": label,
                "rain": rain,
                "min_temp": min_temp,
                "max_temp": max_temp,
                "scope": rain_scope_text(rain)
            })

    return results


@app.route("/")
def index():
    root = fetch_xml_root()
    weather = parse_weather(root)

    return render_template(
        "index.html",
        weather=weather
    )


@app.route("/debug")
def debug():
    root = fetch_xml_root()

    if root is None:
        return {
            "success": False,
            "message": "XML讀取失敗"
        }

    locations = []

    for location in collect_locations(root):
        name = get_location_name(location)

        if name:
            locations.append(name)

    return {
        "success": True,
        "source": URL,
        "pinned": PINNED_LOCATIONS,
        "locations": locations[:100]
    }


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )

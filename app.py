def parse_weather(data):
    results = []

    try:
        locations = data["records"]["Locations"][0]["Location"]
    except:
        return [{
            "location": "資料讀取失敗｜請檢查 API",
            "period": "",
            "rain": "API格式不同",
            "min_temp": "-",
            "max_temp": "-"
        }]

    for loc in locations:
        name = loc["LocationName"]
        elements = {e["ElementName"]: e["Time"] for e in loc["WeatherElement"]}

        for label, start, end in PERIODS:
            rain_probs = []
            temps = []

            if "PoP12h" in elements:
                for t in elements["PoP12h"]:
                    hour = datetime.fromisoformat(t["StartTime"]).hour
                    if start <= hour < end:
                        try:
                            rain_probs.append(int(t["ElementValue"][0]["ProbabilityOfPrecipitation"]))
                        except:
                            pass

            if "MinT" in elements:
                for t in elements["MinT"]:
                    hour = datetime.fromisoformat(t["StartTime"]).hour
                    if start <= hour < end:
                        try:
                            temps.append(int(t["ElementValue"][0]["Temperature"]))
                        except:
                            pass

            rain = max(rain_probs) if rain_probs else 0
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

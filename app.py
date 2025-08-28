from flask import Flask, render_template_string
import requests
from datetime import datetime

app = Flask(__name__)

API_KEY = "5c4ce7f754f9ceefddd179065bc16856"
CITY = "Delhi"

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Weather Dashboard</title>
    <style>
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: linear-gradient(to right, #83a4d4, #b6fbff); margin: 0; padding: 0; text-align: center; }
        h1 { color: #fff; padding: 20px; margin: 0; background: rgba(0,0,0,0.3); }
        .current-card { background: white; padding: 30px; border-radius: 20px; box-shadow: 0 6px 15px rgba(0,0,0,0.2); display: inline-block; margin: 30px auto; }
        .current-temp { font-size: 60px; margin: 15px 0; color: #0077cc; }
        .current-weather { font-size: 24px; color: #444; }
        .date { font-size: 14px; color: #777; }
        .forecast-container { display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; margin: 20px; }
        .forecast-card { background: rgba(255,255,255,0.9); padding: 20px; border-radius: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); width: 160px; transition: transform 0.2s; }
        .forecast-card:hover { transform: scale(1.05); }
        .forecast-date { font-size: 16px; margin-bottom: 10px; font-weight: bold; }
        .forecast-temp { font-size: 28px; margin: 10px 0; color: #0077cc; }
        .forecast-weather { font-size: 16px; color: #444; }
        .weather-icon { width: 60px; height: 60px; }
    </style>
</head>
<body>
    <h1>🌤 Weather Dashboard</h1>

    <!-- Current Weather -->
    <div class="current-card">
        <h2>Current Weather in {{ current.city }}</h2>
        <img class="weather-icon" src="http://openweathermap.org/img/wn/{{ current.icon }}@2x.png" alt="Weather Icon">
        <div class="current-temp">{{ current.temp }}°C</div>
        <div class="current-weather">{{ current.weather }}</div>
        <p class="date">As of: {{ current.date }}</p>
    </div>

    <!-- Forecast Section -->
    <h2 style="color:#fff; margin-top:40px;">📅 5-Day Forecast</h2>
    <div class="forecast-container">
        {% for f in forecast %}
        <div class="forecast-card">
            <div class="forecast-date">{{ f.date }}</div>
            <img class="weather-icon" src="http://openweathermap.org/img/wn/{{ f.icon }}@2x.png" alt="Weather Icon">
            <div class="forecast-temp">{{ f.temp }}°C</div>
            <div class="forecast-weather">{{ f.weather }}</div>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""

@app.route("/")
def home():
    return "✅ Weather Forecast App is running! Go to /forecast for details."

@app.route("/forecast")
def forecast():
    # --- Current Weather ---
    current_url = f"http://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={API_KEY}&units=metric"
    current_res = requests.get(current_url).json()

    if "main" not in current_res:
        return f"<h2>⚠️ Error fetching current weather: {current_res}</h2>"

    current_data = {
        "city": current_res["name"],
        "temp": round(current_res["main"]["temp"], 1),
        "weather": current_res["weather"][0]["description"].title(),
        "icon": current_res["weather"][0]["icon"],
        "date": datetime.fromtimestamp(current_res["dt"]).strftime("%d %b %Y, %I:%M %p")
    }

    # --- 5-Day Forecast (pick ~12:00 noon for each day) ---
    forecast_url = f"http://api.openweathermap.org/data/2.5/forecast?q={CITY}&appid={API_KEY}&units=metric"
    forecast_res = requests.get(forecast_url).json()

    if "list" not in forecast_res:
        return f"<h2>⚠️ Error fetching forecast: {forecast_res}</h2>"

    forecast_data = []
    added_days = set()
    for entry in forecast_res["list"]:
        date_obj = datetime.strptime(entry["dt_txt"], "%Y-%m-%d %H:%M:%S")
        day = date_obj.strftime("%d %b")

        # pick only 12:00 PM entries (to represent the day's weather)
        if date_obj.hour == 12 and day not in added_days:
            forecast_data.append({
                "temp": round(entry["main"]["temp"], 1),
                "weather": entry["weather"][0]["description"].title(),
                "icon": entry["weather"][0]["icon"],
                "date": date_obj.strftime("%a, %d %b")
            })
            added_days.add(day)

    return render_template_string(HTML_TEMPLATE, current=current_data, forecast=forecast_data)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

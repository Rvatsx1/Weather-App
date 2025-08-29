from flask import Flask, render_template_string, request
import requests
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

# Flask setup
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///weather.db'  # database file
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Model (table structure)
class WeatherData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    city = db.Column(db.String(50))
    temp = db.Column(db.Float)
    weather = db.Column(db.String(50))
    date = db.Column(db.String(50))

    def __init__(self, city, temp, weather, date):
        self.city = city
        self.temp = temp
        self.weather = weather
        self.date = date

# ensure DB is created
with app.app_context():
    db.create_all()

API_KEY = "5c4ce7f754f9ceefddd179065bc16856"  # replace with your actual API key

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>🌤 Pro Weather Dashboard</title>
    <style>
        body { font-family: 'Segoe UI', sans-serif; background: linear-gradient(120deg, #89f7fe, #66a6ff); margin: 0; padding: 0; text-align: center; }
        h1 { color: white; padding: 20px; margin: 0; background: rgba(0,0,0,0.4); font-size: 30px; }
        .form-container { margin: 20px; }
        input, button { padding: 12px; font-size: 16px; border-radius: 8px; border: none; }
        button { background: #0077cc; color: white; cursor: pointer; transition: 0.3s; }
        button:hover { background: #005fa3; }
        .error { color: red; font-weight: bold; margin: 20px; }
        .current-card { background: white; padding: 30px; border-radius: 20px; box-shadow: 0 6px 15px rgba(0,0,0,0.2); display: inline-block; margin: 30px auto; width: 400px; }
        .info { font-size: 16px; color: #444; margin: 10px 0; }
        .current-temp { font-size: 70px; margin: 15px 0; color: #0077cc; }
        .forecast-container { display: flex; justify-content: center; gap: 20px; flex-wrap: wrap; margin: 20px; }
        .forecast-card { background: rgba(255,255,255,0.9); padding: 20px; border-radius: 15px; box-shadow: 0 4px 10px rgba(0,0,0,0.1); width: 160px; transition: transform 0.2s; }
        .forecast-card:hover { transform: scale(1.05); }
        .forecast-date { font-weight: bold; margin-bottom: 8px; }
        .weather-icon { width: 60px; height: 60px; }
    </style>
    <script> function showError(msg) { alert(msg); } </script>
</head>
<body>
    <h1>🌤 Pro Weather Dashboard</h1>
    <!-- Search box -->
    <div class="form-container">
        <form method="POST" action="/">
            <input type="text" name="city" placeholder="Enter City (e.g. Delhi)" required>
            <button type="submit">Get Weather</button>
        </form>
    </div>
    {% if error %}
        <div class="error">⚠️ {{ error }}</div>
        <script>showError("{{ error }}");</script>
    {% endif %}
    {% if current %}
    <!-- Current Weather -->
    <div class="current-card">
        <h2>{{ current.city }}</h2>
        <img class="weather-icon" src="http://openweathermap.org/img/wn/{{ current.icon }}@2x.png" alt="Weather Icon">
        <div class="current-temp">{{ current.temp }}°C</div>
        <div class="info">{{ current.weather }}</div>
        <div class="info">💧 Humidity: {{ current.humidity }}%</div>
        <div class="info">💨 Wind: {{ current.wind }} m/s</div>
        <div class="info">🌅 Sunrise: {{ current.sunrise }}</div>
        <div class="info">🌇 Sunset: {{ current.sunset }}</div>
        <p class="date">Last Updated: {{ current.date }}</p>
    </div>
    <!-- Forecast Section -->
    <h2 style="color:white; margin-top:40px;">📅 5-Day Forecast</h2>
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
    {% endif %}
</body>
</html>
"""

@app.route("/", methods=["GET", "POST"])
def home():
    selected_city = "Delhi"
    error = None
    current_data = None
    forecast_data = []

    if request.method == "POST":
        selected_city = request.form.get("city").strip()
        if not selected_city:
            error = "Please enter a valid city!"
            return render_template_string(HTML_TEMPLATE, error=error, current=None, forecast=[])

    # Current weather
    current_url = f"http://api.openweathermap.org/data/2.5/weather?q={selected_city}&appid={API_KEY}&units=metric"
    current_res = requests.get(current_url).json()
    if "main" not in current_res:
        error = f"⚠️ Could not fetch weather for {selected_city}. Try another city."
        return render_template_string(HTML_TEMPLATE, error=error, current=None, forecast=[])

    current_data = {
        "city": current_res["name"],
        "temp": round(current_res["main"]["temp"], 1),
        "weather": current_res["weather"][0]["description"].title(),
        "icon": current_res["weather"][0]["icon"],
        "humidity": current_res["main"]["humidity"],
        "wind": current_res["wind"]["speed"],
        "sunrise": datetime.fromtimestamp(current_res["sys"]["sunrise"]).strftime("%I:%M %p"),
        "sunset": datetime.fromtimestamp(current_res["sys"]["sunset"]).strftime("%I:%M %p"),
        "date": datetime.fromtimestamp(current_res["dt"]).strftime("%d %b %Y, %I:%M %p")
    }

    # save to DB
    weather_entry = WeatherData(
        city=current_data["city"],
        temp=current_data["temp"],
        weather=current_data["weather"],
        date=current_data["date"]
    )
    db.session.add(weather_entry)
    db.session.commit()

    # Forecast
    forecast_url = f"http://api.openweathermap.org/data/2.5/forecast?q={selected_city}&appid={API_KEY}&units=metric"
    forecast_res = requests.get(forecast_url).json()
    added_days = set()
    for entry in forecast_res.get("list", []):
        date_obj = datetime.strptime(entry["dt_txt"], "%Y-%m-%d %H:%M:%S")
        day = date_obj.strftime("%d %b")
        if date_obj.hour == 12 and day not in added_days:
            forecast_data.append({
                "temp": round(entry["main"]["temp"], 1),
                "weather": entry["weather"][0]["description"].title(),
                "icon": entry["weather"][0]["icon"],
                "date": date_obj.strftime("%a, %d %b")
            })
            added_days.add(day)

    return render_template_string(HTML_TEMPLATE, error=error, current=current_data, forecast=forecast_data)

# 🆕 new route to check DB history
@app.route("/history")
def history():
    records = WeatherData.query.all()
    table_html = "<h2>📜 Search History</h2><table border=1 cellpadding=10><tr><th>City</th><th>Temp (°C)</th><th>Weather</th><th>Date</th></tr>"
    for r in records:
        table_html += f"<tr><td>{r.city}</td><td>{r.temp}</td><td>{r.weather}</td><td>{r.date}</td></tr>"
    table_html += "</table>"
    return table_html

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

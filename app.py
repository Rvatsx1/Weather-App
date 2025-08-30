from flask import Flask, render_template_string, request, send_file
import requests
from datetime import datetime, timedelta
from flask_sqlalchemy import SQLAlchemy
import os
from openpyxl import Workbook

# Flask setup
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///weather.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Database Model
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

API_KEY = "5c4ce7f754f9ceefddd179065bc16856"  # replace with your actual API key

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>🌤 Pro Weather Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; background: linear-gradient(120deg, #89f7fe, #66a6ff); text-align: center; margin: 0; }
        h1 { background: rgba(0,0,0,0.4); color: white; padding: 15px; }
        .form-container { margin: 20px; }
        input, button { padding: 10px; font-size: 16px; border-radius: 6px; border: none; }
        button { background: #0077cc; color: white; cursor: pointer; }
        button:hover { background: #005fa3; }
        .error { color: red; font-weight: bold; margin: 20px; }
        .current-card { background: white; padding: 25px; margin: 20px auto; border-radius: 15px; width: 400px; }
        .forecast-container { display: flex; justify-content: center; flex-wrap: wrap; gap: 15px; }
        .forecast-card { background: #fff; padding: 15px; border-radius: 10px; width: 150px; }
        .weather-icon { width: 50px; height: 50px; }
    </style>
</head>
<body>
    <h1>🌤 Pro Weather Dashboard</h1>

    <!-- Search -->
    <div class="form-container">
        <form method="POST" action="/">
            <input type="text" name="city" placeholder="Enter City" value="{{ selected_city }}" required>
            <button type="submit">Get Weather</button>
        </form>
        <br>
        <a href="/history"><button type="button">📜 View History</button></a>
    </div>

    {% if error %}
        <div class="error">⚠️ {{ error }}</div>
    {% endif %}

    {% if current %}
    <div class="current-card">
        <h2>{{ current.city }}</h2>
        <img class="weather-icon" src="http://openweathermap.org/img/wn/{{ current.icon }}@2x.png">
        <h3>{{ current.temp }}°C</h3>
        <p>{{ current.weather }}</p>
        <p>💧 Humidity: {{ current.humidity }}%</p>
        <p>💨 Wind: {{ current.wind }} m/s</p>
        <p>🌅 Sunrise: {{ current.sunrise }} | 🌇 Sunset: {{ current.sunset }}</p>
        <p>📅 {{ current.date }}</p>
    </div>

    <h2 style="color:white;">📅 5-Day Forecast</h2>
    <div class="forecast-container">
        {% for f in forecast %}
        <div class="forecast-card">
            <p><b>{{ f.date }}</b></p>
            <img class="weather-icon" src="http://openweathermap.org/img/wn/{{ f.icon }}@2x.png">
            <p>{{ f.temp }}°C</p>
            <p>{{ f.weather }}</p>
        </div>
        {% endfor %}
    </div>
    {% endif %}
</body>
</html>
"""

HISTORY_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>📜 Weather History</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f4f6f9; text-align: center; }
        h1 { background: #0077cc; color: white; padding: 15px; }
        table { margin: 20px auto; border-collapse: collapse; width: 80%; }
        th, td { border: 1px solid #ddd; padding: 10px; }
        th { background: #0077cc; color: white; }
        tr:nth-child(even) { background: #f9f9f9; }
        a button { margin: 20px; padding: 10px; font-size: 16px; border-radius: 6px; border: none; background: #0077cc; color: white; cursor: pointer; }
        a button:hover { background: #005fa3; }
    </style>
</head>
<body>
    <h1>📜 Search History</h1>
    <table>
        <tr><th>City</th><th>Temperature (°C)</th><th>Weather</th><th>Date</th></tr>
        {% for row in history %}
        <tr>
            <td>{{ row.city }}</td>
            <td>{{ row.temp }}</td>
            <td>{{ row.weather }}</td>
            <td>{{ row.date }}</td>
        </tr>
        {% endfor %}
    </table>
    <a href="/download_excel"><button>⬇ Download Last 5 Days (Excel)</button></a>
    <a href="/"><button>⬅ Back to Dashboard</button></a>
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
        selected_city = request.form.get("city")

    # Current Weather
    current_url = f"http://api.openweathermap.org/data/2.5/weather?q={selected_city}&appid={API_KEY}&units=metric"
    current_res = requests.get(current_url).json()

    if "main" not in current_res:
        error = "Error fetching weather!"
        return render_template_string(HTML_TEMPLATE, selected_city=selected_city, error=error, current=None, forecast=[])

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

    # Save to DB
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
    for entry in forecast_res["list"]:
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

    return render_template_string(HTML_TEMPLATE, selected_city=selected_city, error=error, current=current_data, forecast=forecast_data)

@app.route("/history")
def history():
    records = WeatherData.query.all()
    return render_template_string(HISTORY_TEMPLATE, history=records)

@app.route("/download_excel")
def download_excel():
    # Get last 5 days of history
    cutoff = datetime.now() - timedelta(days=5)
    records = WeatherData.query.all()

    # Create Excel file
    wb = Workbook()
    ws = wb.active
    ws.title = "Weather History"
    ws.append(["City", "Temperature (°C)", "Weather", "Date"])

    for row in records:
        ws.append([row.city, row.temp, row.weather, row.date])

    filepath = "weather_history.xlsx"
    wb.save(filepath)

    return send_file(filepath, as_attachment=True)

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True, host="0.0.0.0", port=5000)

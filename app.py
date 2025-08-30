from flask import Flask, render_template, request, session, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
import requests
import os
from dotenv import load_dotenv
import logging
from typing import Optional, Dict, Any, List
import pandas as pd
from io import BytesIO
import uuid

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-fallback-key')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///aura_weather.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)

db = SQLAlchemy(app)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Keys
OWM_API_KEY = os.environ.get('OWM_API_KEY')

# --- Database Models ---
class UserLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(80))
    city = db.Column(db.String(100), nullable=False)
    country = db.Column(db.String(100))
    country_code = db.Column(db.String(2))
    is_favorite = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    def __repr__(self):
        return f'<UserLocation {self.city}>'

# --- Service Layer: Data Acquisition ---
class WeatherDataService:
    @staticmethod
    def fetch_primary_data(city: str) -> Optional[Dict[str, Any]]:
        """Fetches data from the primary source (OpenWeatherMap)."""
        try:
            current_url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric"
            forecast_url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={OWM_API_KEY}&units=metric"

            current_res = requests.get(current_url, timeout=10)
            current_res.raise_for_status()
            current_data = current_res.json()

            if current_data.get('cod') != 200:
                return None

            forecast_res = requests.get(forecast_url, timeout=10)
            forecast_res.raise_for_status()
            forecast_data = forecast_res.json()

            return {'current': current_data, 'forecast': forecast_data}

        except requests.exceptions.RequestException as e:
            logger.error(f"Primary API request failed for {city}: {e}")
            return None

    @staticmethod
    def fetch_air_quality_data(lat: float, lon: float) -> Optional[Dict[str, Any]]:
        """Fetches Air Quality Data from the Open-Meteo API."""
        try:
            url = f"https://air-quality-api.open-meteo.com/v1/air-quality?latitude={lat}&longitude={lon}&current=us_aqi,pm10,pm2_5,carbon_monoxide&timezone=auto"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            aqi_data = response.json()
            
            if 'current' not in aqi_data or 'time' not in aqi_data['current']:
                return None
                
            return aqi_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Open-Meteo AQI API request failed: {e}")
            return None

    @staticmethod
    def parse_weather_data(api_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not api_data:
            return None

        c = api_data['current']
        timezone_offset = c.get("timezone", 0)
        local_time = (datetime.now(timezone.utc) + timedelta(seconds=timezone_offset))

        lat = c['coord']['lat']
        lon = c['coord']['lon']
        
        aqi_data = WeatherDataService.fetch_air_quality_data(lat, lon)
        current_aqi = "N/A"
        current_pm25 = "N/A"
        current_pm10 = "N/A"
        current_co = "N/A"
        
        if aqi_data and 'current' in aqi_data:
            current = aqi_data['current']
            current_aqi = current.get('us_aqi', 'N/A')
            current_pm25 = round(current.get('pm2_5', 'N/A'), 1)
            current_pm10 = round(current.get('pm10', 'N/A'), 1)
            current_co = round(current.get('carbon_monoxide', 'N/A'), 1)

        current_dict = {
            "city": c["name"],
            "country": c["sys"]["country"],
            "country_code": c["sys"]["country"].lower(),
            "temp": round(c["main"]["temp"], 1),
            "feels_like": round(c["main"]["feels_like"], 1),
            "weather": c["weather"][0]["description"].title(),
            "icon": c["weather"][0]["icon"],
            "humidity": c["main"]["humidity"],
            "wind_speed": c["wind"]["speed"],
            "wind_deg": c["wind"].get('deg', 0),
            "pressure": c["main"]["pressure"],
            "sunrise": datetime.fromtimestamp(c["sys"]["sunrise"]).strftime("%H:%M"),
            "sunset": datetime.fromtimestamp(c["sys"]["sunset"]).strftime("%H:%M"),
            "timezone_offset": timezone_offset,
            "local_time": local_time.strftime("%d %b %Y, %H:%M"),
            "date_updated": datetime.fromtimestamp(c["dt"]).strftime("%d %b %Y, %H:%M"),
            "aqi": current_aqi,
            "pm25": current_pm25,
            "pm10": current_pm10,
            "co": current_co,
            "lat": lat,
            "lon": lon
        }

        forecast_list = []
        added_days = set()
        for entry in api_data['forecast'].get("list", []):
            date_obj = datetime.strptime(entry["dt_txt"], "%Y-%m-%d %H:%M:%S")
            day = date_obj.strftime("%Y-%m-%d")
            if date_obj.hour == 12 and day not in added_days:
                forecast_list.append({
                    "temp": round(entry["main"]["temp"], 1),
                    "temp_min": round(entry["main"]["temp_min"], 1),
                    "temp_max": round(entry["main"]["temp_max"], 1),
                    "weather": entry["weather"][0]["description"].title(),
                    "icon": entry["weather"][0]["icon"],
                    "date": date_obj.strftime("%a"),
                    "full_date": date_obj.strftime("%d %b"),
                    "precip_prob": round(entry.get('pop', 0) * 100)
                })
                added_days.add(day)

        return {'current': current_dict, 'forecast': forecast_list}

# --- Flask Routes ---
@app.route("/", methods=["GET", "POST"])
def home():
    if 'user_id' not in session:
        session.permanent = True
        session['user_id'] = str(uuid.uuid4())
        session['default_city'] = 'Delhi'

    default_city = session.get('default_city', 'Delhi')
    city_query = request.form.get('city', default_city)
    error = None
    weather_data = None

    raw_data = WeatherDataService.fetch_primary_data(city_query)
    if raw_data:
        weather_data = WeatherDataService.parse_weather_data(raw_data)
        session['default_city'] = city_query
        session['last_city'] = city_query

        try:
            existing_location = UserLocation.query.filter_by(
                user_id=session['user_id'],
                city=weather_data['current']['city']
            ).first()

            if not existing_location:
                new_location = UserLocation(
                    user_id=session['user_id'],
                    city=weather_data['current']['city'],
                    country=weather_data['current']['country'],
                    country_code=weather_data['current']['country_code']
                )
                db.session.add(new_location)
                db.session.commit()
        except Exception as e:
            logger.error(f"Failed to save location to history: {e}")
            db.session.rollback()

    elif request.method == 'POST':
        error = "City not found or API error. Please try again."

    user_locations = UserLocation.query.filter_by(user_id=session['user_id']).order_by(UserLocation.created_at.desc()).limit(5).all()

    theme_class = "theme-default"
    if weather_data and weather_data['current']:
        time_str = weather_data['current']['local_time']
        try:
            hour = datetime.strptime(time_str, "%d %b %Y, %H:%M").hour
            if 6 <= hour < 18:
                theme_class = "theme-day"
            else:
                theme_class = "theme-night"
        except ValueError:
            pass

    return render_template(
        'index.html',
        weather=weather_data,
        error=error,
        user_locations=user_locations,
        theme_class=theme_class
    )

@app.route("/export/<city>")
def export_forecast(city):
    raw_data = WeatherDataService.fetch_primary_data(city)
    if not raw_data:
        return "Error: Could not fetch data for this city.", 404

    weather_data = WeatherDataService.parse_weather_data(raw_data)
    if not weather_data:
        return "Error: Could not parse data for this city.", 404

    forecast_list = weather_data['forecast']
    df_data = []
    for day in forecast_list:
        df_data.append({
            'Date': day['full_date'],
            'Day': day['date'],
            'Temperature (°C)': day['temp'],
            'Min Temp (°C)': day['temp_min'],
            'Max Temp (°C)': day['temp_max'],
            'Condition': day['weather'],
            'Precipitation Chance (%)': day['precip_prob']
        })

    df = pd.DataFrame(df_data)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='5-Day Forecast', index=False)
        
    output.seek(0)

    current_date = datetime.now().strftime("%Y-%m-%d")
    filename = f"Aura_Forecast_{city}_{current_date}.xlsx"

    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

# --- Application Context & Startup ---
with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
    
# --- Production Configuration ---
if __name__ == "__main__":
    # This block only runs when executed directly, not when imported
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
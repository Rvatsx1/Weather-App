import os
from flask import Flask, render_template, request, session, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta, timezone
import requests
import logging
from dotenv import load_dotenv
import pandas as pd
from io import BytesIO
import uuid

# Load env variables
load_dotenv()

# Create Flask app with explicit template folder
app = Flask(__name__, template_folder='templates')
app.secret_key = os.environ.get("SECRET_KEY", "dev-fallback-key-12345")

# --- Database config ---
db_url = os.environ.get("DATABASE_URL", "sqlite:///aura_weather.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=7)

db = SQLAlchemy(app)

# Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API Keys
OWM_API_KEY = os.environ.get("OWM_API_KEY")

# --- DB Model ---
class UserLocation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(80))
    city = db.Column(db.String(100), nullable=False)
    country = db.Column(db.String(100))
    country_code = db.Column(db.String(2))
    is_favorite = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.now(timezone.utc))

    def __repr__(self):
        return f"<UserLocation {self.city}, {self.country}>"

# --- Weather service helpers ---
class WeatherDataService:
    @staticmethod
    def fetch_primary_data(city: str):
        if not OWM_API_KEY:
            logger.error("OWM_API_KEY not found in environment variables")
            return None
        
        try:
            current_url = f"http://api.openweathermap.org/data/2.5/weather?q={city}&appid={OWM_API_KEY}&units=metric"
            forecast_url = f"http://api.openweathermap.org/data/2.5/forecast?q={city}&appid={OWM_API_KEY}&units=metric"
            
            current_res = requests.get(current_url, timeout=10)
            current_res.raise_for_status()
            current_data = current_res.json()
            
            if current_data.get("cod") != 200:
                logger.error(f"API returned error code: {current_data.get('cod')}")
                return None
            
            forecast_res = requests.get(forecast_url, timeout=10)
            forecast_res.raise_for_status()
            forecast_data = forecast_res.json()
            
            return {"current": current_data, "forecast": forecast_data}
        
        except requests.exceptions.RequestException as e:
            logger.error(f"Primary API request failed for {city}: {e}")
            return None

    @staticmethod
    def parse_weather_data(api_data):
        if not api_data:
            return None
        
        try:
            c = api_data["current"]
            timezone_offset = c.get("timezone", 0)
            local_time = datetime.now(timezone.utc) + timedelta(seconds=timezone_offset)
            
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
                "pressure": c["main"]["pressure"],
                "local_time": local_time.strftime("%d %b %Y, %H:%M"),
            }

            forecast_list = []
            added_days = set()
            
            for entry in api_data["forecast"].get("list", []):
                date_obj = datetime.strptime(entry["dt_txt"], "%Y-%m-%d %H:%M:%S")
                day = date_obj.strftime("%Y-%m-%d")
                
                if date_obj.hour == 12 and day not in added_days:
                    forecast_list.append({
                        "temp": round(entry["main"]["temp"], 1),
                        "weather": entry["weather"][0]["description"].title(),
                        "icon": entry["weather"][0]["icon"],
                        "date": date_obj.strftime("%a"),
                    })
                    added_days.add(day)

            return {"current": current_dict, "forecast": forecast_list}
        
        except (KeyError, TypeError, ValueError) as e:
            logger.error(f"Error parsing weather data: {e}")
            return None

# --- Routes ---
@app.route("/", methods=["GET", "POST"])
def home():
    if "user_id" not in session:
        session.permanent = True
        session["user_id"] = str(uuid.uuid4())
        session["default_city"] = "Delhi"

    default_city = session.get("default_city", "Delhi")
    city_query = request.form.get("city", default_city)
    
    error = None
    weather_data = None

    if city_query:
        raw_data = WeatherDataService.fetch_primary_data(city_query)
        if raw_data:
            weather_data = WeatherDataService.parse_weather_data(raw_data)
            if weather_data:
                session["default_city"] = city_query
            else:
                error = "Unable to process weather data."
        elif request.method == "POST":
            error = "City not found or API error. Please check your city name."

    return render_template("index.html", weather=weather_data, error=error)

@app.route("/export/<city>")
def export_forecast(city):
    raw_data = WeatherDataService.fetch_primary_data(city)
    if not raw_data:
        return "Error: Could not fetch weather data.", 404

    weather_data = WeatherDataService.parse_weather_data(raw_data)
    if not weather_data:
        return "Error: Could not parse weather data.", 404

    forecast_list = weather_data["forecast"]
    df = pd.DataFrame(forecast_list)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Forecast", index=False)
    
    output.seek(0)
    filename = f"Aura_Forecast_{city}_{datetime.now().strftime('%Y-%m-%d')}.xlsx"
    
    return send_file(output, as_attachment=True, download_name=filename,
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/health")
def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

# --- Initialize DB safely ---
def create_tables():
    """Create database tables if they don't exist"""
    try:
        with app.app_context():
            db.create_all()
            logger.info("Database tables created successfully")
    except Exception as e:
        logger.warning(f"Database initialization failed: {e}")

# Initialize database
create_tables()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
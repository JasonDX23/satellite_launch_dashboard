from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import httpx
import json
import os

app = FastAPI(title="Launch Weather Intelligence API")

# Load Launchpads
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
with open(os.path.join(DATA_DIR, "launchpads.json"), "r") as f:
    geojson_data = json.load(f)

# Extract the features from the GeoJSON and format them for the dashboard
LAUNCHPADS = []
for feature in geojson_data.get("features", []):
    props = feature["properties"]
    LAUNCHPADS.append({
        # Since your GeoJSON "id" is null, we'll use "Name" as the unique identifier
        "id": props.get("Name"), 
        "name": props.get("Name"),
        "lat": props.get("lat"),
        "lon": props.get("lon"),
        "country": props.get("description", "Unknown")
    })

# Build the dictionary mapping IDs to the site data
PADS_DB = {pad["id"]: pad for pad in LAUNCHPADS}
# Hardcoded LCC Constraints (Simplified Baseline)
LCC_RULES = {
    "max_surface_wind_kmh": 55,  # ~30 kts
    "max_precipitation_mm": 0.1, # No rain
    "max_cape_jkg": 1000,        # Thunderstorm potential
    "max_cloud_cover_percent": 80, # Thick cloud rule
    "min_visibility_m": 4800     # Minimum safe visibility (3 miles)
}

async def fetch_weather_data(lat: float, lon: float):
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "temperature_2m,windspeed_10m,winddirection_10m,precipitation,cape,cloudcover,visibility",
        "timezone": "UTC",
        "forecast_days": 7
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        response.raise_for_status()
        return response.json()

def evaluate_lcc(hourly_data):
    """Evaluates weather against Launch Commit Criteria."""
    timeline = []
    for i in range(len(hourly_data["time"])):
        wind = hourly_data["windspeed_10m"][i]
        precip = hourly_data["precipitation"][i]
        cape = hourly_data["cape"][i]
        clouds = hourly_data["cloudcover"][i]
        vis = hourly_data["visibility"][i]
        
        # Rule checks
        violations = []
        if wind > LCC_RULES["max_surface_wind_kmh"]:
            violations.append(f"High Wind ({wind} km/h)")
        if precip > LCC_RULES["max_precipitation_mm"]:
            violations.append(f"Precipitation ({precip} mm)")
        if cape > LCC_RULES["max_cape_jkg"]:
            violations.append(f"High CAPE ({cape} J/kg)")
        if clouds > LCC_RULES["max_cloud_cover_percent"]:
            violations.append(f"Thick Clouds ({clouds}%)")
        if vis < LCC_RULES["min_visibility_m"]:
            violations.append(f"Poor Visibility ({vis/1000:.1f} km)")
            
        status = "GO" if not violations else "NO-GO"
        
        timeline.append({
            "time": hourly_data["time"][i],
            "temp": hourly_data["temperature_2m"][i],
            "wind": wind,
            "precip": precip,
            "cape": cape,
            "clouds": clouds,
            "visibility": vis,
            "status": status,
            "violations": violations
        })
    return timeline

@app.get("/api/sites")
def get_sites():
    return LAUNCHPADS

@app.get("/api/weather/{site_id}")
async def get_site_weather(site_id: str):
    if site_id not in PADS_DB:
        raise HTTPException(status_code=404, detail="Launch site not found")
    
    site = PADS_DB[site_id]
    raw_weather = await fetch_weather_data(site["lat"], site["lon"])
    timeline = evaluate_lcc(raw_weather["hourly"])
    
    return {
        "site": site,
        "forecast": timeline
    }

# Mount frontend (safely for Vercel)
frontend_dir = os.path.join(os.path.dirname(__file__), "../frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(frontend_dir, "index.html"))
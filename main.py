"""
CascadeWatch — Multi-Hazard Cascade Risk Engine
Hackathon Prototype Backend
"""

import asyncio
import math
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI(title="CascadeWatch", version="0.1.0")

# ---------------------------------------------------------------------------
# HISTORICAL CASCADE PATTERNS — the knowledge base
# ---------------------------------------------------------------------------

CASCADE_PATTERNS = [
    {
        "id": "eq_landslide",
        "name": "Earthquake → Landslide",
        "chain": ["earthquake", "landslide"],
        "description": "Seismic activity destabilises slopes already weakened by rain or deforestation, triggering landslides hours to days later.",
        "factors": [
            {"name": "quake_magnitude", "weight": 0.25, "label": "Earthquake Magnitude"},
            {"name": "slope_steepness", "weight": 0.20, "label": "Slope Steepness"},
            {"name": "soil_saturation", "weight": 0.25, "label": "Soil Saturation"},
            {"name": "deforestation", "weight": 0.15, "label": "Deforestation %"},
            {"name": "historical_precedent", "weight": 0.15, "label": "Historical Precedent"},
        ],
        "threshold": 0.70,
    },
    {
        "id": "rain_flood",
        "name": "Heavy Rain → Flash Flood → Infrastructure Failure",
        "chain": ["heavy_rain", "flood", "infrastructure_failure"],
        "description": "Prolonged or extreme rainfall saturates already-wet ground, overwhelms drainage, and can breach dams or levees.",
        "factors": [
            {"name": "rainfall_intensity", "weight": 0.25, "label": "Rainfall Intensity"},
            {"name": "soil_saturation", "weight": 0.20, "label": "Soil Saturation"},
            {"name": "elevation_risk", "weight": 0.20, "label": "Low Elevation / Flood Plain"},
            {"name": "dam_proximity", "weight": 0.15, "label": "Upstream Dam Proximity"},
            {"name": "drainage_landcover", "weight": 0.20, "label": "Poor Drainage / Impervious Cover"},
        ],
        "threshold": 0.65,
    },
    {
        "id": "eq_tsunami",
        "name": "Earthquake → Tsunami → Coastal Destruction",
        "chain": ["earthquake", "tsunami", "coastal_destruction"],
        "description": "Shallow undersea earthquake displaces water, generating a tsunami that strikes populated coastlines.",
        "factors": [
            {"name": "quake_magnitude", "weight": 0.30, "label": "Earthquake Magnitude"},
            {"name": "quake_depth_shallow", "weight": 0.25, "label": "Shallow Depth"},
            {"name": "ocean_floor", "weight": 0.20, "label": "Undersea Location"},
            {"name": "coastal_population", "weight": 0.15, "label": "Coastal Population Density"},
            {"name": "historical_precedent", "weight": 0.10, "label": "Historical Precedent"},
        ],
        "threshold": 0.60,
    },
    {
        "id": "heat_drought_fire",
        "name": "Heatwave → Drought → Wildfire",
        "chain": ["heatwave", "drought", "wildfire"],
        "description": "Sustained high temperatures dry out vegetation; the resulting tinder-like conditions make large wildfires inevitable.",
        "factors": [
            {"name": "temperature_anomaly", "weight": 0.25, "label": "Temperature Anomaly"},
            {"name": "precipitation_deficit", "weight": 0.25, "label": "Precipitation Deficit"},
            {"name": "vegetation_dryness", "weight": 0.20, "label": "Vegetation Dryness"},
            {"name": "wind_speed", "weight": 0.15, "label": "Wind Speed"},
            {"name": "historical_precedent", "weight": 0.15, "label": "Historical Precedent"},
        ],
        "threshold": 0.65,
    },
]

# ---------------------------------------------------------------------------
# MONITORED REGIONS with terrain/context profiles
# ---------------------------------------------------------------------------

REGIONS = [
    {
        "id": "uttarakhand",
        "name": "Uttarakhand, India",
        "lat": 30.73,
        "lon": 79.07,
        "slope_steepness": 0.85,
        "deforestation": 0.40,
        "elevation_risk": 0.30,
        "dam_proximity": 0.75,
        "drainage_landcover": 0.55,
        "coastal_population": 0.0,
        "ocean_floor": 0.0,
        "historical_precedent": 0.90,
        "description": "Himalayan state with steep terrain, glacial lakes, and monsoon exposure.",
    },
    {
        "id": "nepal_central",
        "name": "Central Nepal",
        "lat": 28.39,
        "lon": 84.12,
        "slope_steepness": 0.80,
        "deforestation": 0.35,
        "elevation_risk": 0.35,
        "dam_proximity": 0.40,
        "drainage_landcover": 0.45,
        "coastal_population": 0.0,
        "ocean_floor": 0.0,
        "historical_precedent": 0.85,
        "description": "Seismically active Himalayan zone with dense hillside settlements.",
    },
    {
        "id": "tohoku",
        "name": "Tōhoku, Japan",
        "lat": 38.30,
        "lon": 142.37,
        "slope_steepness": 0.30,
        "deforestation": 0.10,
        "elevation_risk": 0.70,
        "dam_proximity": 0.50,
        "drainage_landcover": 0.30,
        "coastal_population": 0.85,
        "ocean_floor": 0.95,
        "historical_precedent": 0.95,
        "description": "Pacific coast with subduction zone — history of major tsunamis.",
    },
    {
        "id": "california",
        "name": "Southern California, USA",
        "lat": 34.05,
        "lon": -118.24,
        "slope_steepness": 0.55,
        "deforestation": 0.25,
        "elevation_risk": 0.40,
        "dam_proximity": 0.35,
        "drainage_landcover": 0.60,
        "coastal_population": 0.70,
        "ocean_floor": 0.15,
        "historical_precedent": 0.75,
        "description": "Fire-prone chaparral, seismic faults, and periodic drought cycles.",
    },
    {
        "id": "puerto_rico",
        "name": "Puerto Rico",
        "lat": 18.22,
        "lon": -66.59,
        "slope_steepness": 0.50,
        "deforestation": 0.30,
        "elevation_risk": 0.65,
        "dam_proximity": 0.55,
        "drainage_landcover": 0.60,
        "coastal_population": 0.80,
        "ocean_floor": 0.40,
        "historical_precedent": 0.70,
        "description": "Hurricane corridor with aging infrastructure and mountainous interior.",
    },
    {
        "id": "turkey_se",
        "name": "SE Turkey (Hatay–Gaziantep)",
        "lat": 37.00,
        "lon": 37.35,
        "slope_steepness": 0.35,
        "deforestation": 0.20,
        "elevation_risk": 0.45,
        "dam_proximity": 0.40,
        "drainage_landcover": 0.35,
        "coastal_population": 0.30,
        "ocean_floor": 0.0,
        "historical_precedent": 0.80,
        "description": "East Anatolian Fault zone — site of the devastating 2023 earthquake sequence.",
    },
]

REGION_MAP = {r["id"]: r for r in REGIONS}

# ---------------------------------------------------------------------------
# HISTORICAL REPLAY EVENTS (curated data points for demo)
# ---------------------------------------------------------------------------

REPLAY_EVENTS = {
    "uttarakhand_2013": {
        "name": "Uttarakhand Flood Disaster 2013",
        "region_id": "uttarakhand",
        "summary": "An unusually early monsoon combined with glacial lake overflow and a cloudburst caused massive flooding and landslides, killing nearly 6,000 people.",
        "death_toll": "~5,700",
        "timeline": [
            {
                "date": "2013-06-01",
                "day_label": "June 1 – Early monsoon arrives",
                "conditions": {
                    "rainfall_intensity": 0.35,
                    "soil_saturation": 0.40,
                    "quake_magnitude": 0.0,
                    "temperature_anomaly": 0.20,
                    "precipitation_deficit": 0.0,
                    "vegetation_dryness": 0.10,
                    "wind_speed": 0.20,
                },
                "narrative": "Monsoon arrives 2 weeks early. Rainfall is above normal but not extreme. Soil begins absorbing water. Conventional weather systems see nothing alarming.",
            },
            {
                "date": "2013-06-07",
                "day_label": "June 7 – Continuous rain, soil saturating",
                "conditions": {
                    "rainfall_intensity": 0.50,
                    "soil_saturation": 0.60,
                    "quake_magnitude": 0.0,
                    "temperature_anomaly": 0.25,
                    "precipitation_deficit": 0.0,
                    "vegetation_dryness": 0.05,
                    "wind_speed": 0.25,
                },
                "narrative": "A week of continuous rain. Soil moisture is climbing past saturation. Glacial lakes in upper Kedarnath valley are swelling. Still no individual alert threshold breached.",
            },
            {
                "date": "2013-06-12",
                "day_label": "June 12 – Ground near saturation",
                "conditions": {
                    "rainfall_intensity": 0.60,
                    "soil_saturation": 0.78,
                    "quake_magnitude": 0.0,
                    "temperature_anomaly": 0.30,
                    "precipitation_deficit": 0.0,
                    "vegetation_dryness": 0.05,
                    "wind_speed": 0.30,
                },
                "narrative": "Soil is nearly saturated on steep, partially deforested slopes. Upstream lakes are at dangerous capacity. CascadeWatch would flag MODERATE risk here — rain + saturated soil + steep slopes + deforestation = landslide preconditions forming.",
            },
            {
                "date": "2013-06-14",
                "day_label": "June 14 – ⚠️ CascadeWatch: HIGH RISK",
                "conditions": {
                    "rainfall_intensity": 0.75,
                    "soil_saturation": 0.88,
                    "quake_magnitude": 0.05,
                    "temperature_anomaly": 0.35,
                    "precipitation_deficit": 0.0,
                    "vegetation_dryness": 0.05,
                    "wind_speed": 0.35,
                },
                "narrative": "CascadeWatch fires HIGH CASCADE ALERT. Rainfall intensity rising, soil fully saturated, steep deforested slopes. The system detects the pattern matches 3 prior catastrophic landslide-flood events in this region. 48 hours before disaster. Evacuation advisory recommended.",
            },
            {
                "date": "2013-06-16",
                "day_label": "June 16 – Cloudburst → catastrophe",
                "conditions": {
                    "rainfall_intensity": 0.95,
                    "soil_saturation": 0.98,
                    "quake_magnitude": 0.05,
                    "temperature_anomaly": 0.35,
                    "precipitation_deficit": 0.0,
                    "vegetation_dryness": 0.05,
                    "wind_speed": 0.50,
                },
                "narrative": "A massive cloudburst strikes Kedarnath. Chorabari glacial lake breaches. The saturated slopes give way. Massive landslides and flash floods sweep through valleys. Nearly 6,000 people perish. Individual weather systems only issued a heavy-rain warning — none predicted the cascade.",
            },
            {
                "date": "2013-06-17",
                "day_label": "June 17 – Aftermath",
                "conditions": {
                    "rainfall_intensity": 0.60,
                    "soil_saturation": 0.99,
                    "quake_magnitude": 0.0,
                    "temperature_anomaly": 0.30,
                    "precipitation_deficit": 0.0,
                    "vegetation_dryness": 0.05,
                    "wind_speed": 0.20,
                },
                "narrative": "Rain subsides but slopes continue to collapse. Roads are washed away. Rescue operations are impossible for days. The cascade has played out in full.",
            },
        ],
    },
    "nepal_2015": {
        "name": "Nepal Earthquake Cascade 2015",
        "region_id": "nepal_central",
        "summary": "A M7.8 earthquake triggered hundreds of landslides on rain-weakened slopes and dammed rivers, creating ongoing flood risk for months.",
        "death_toll": "~8,900",
        "timeline": [
            {
                "date": "2015-04-15",
                "day_label": "April 15 – Pre-monsoon rain begins",
                "conditions": {
                    "rainfall_intensity": 0.30,
                    "soil_saturation": 0.35,
                    "quake_magnitude": 0.0,
                    "temperature_anomaly": 0.15,
                    "precipitation_deficit": 0.0,
                    "vegetation_dryness": 0.15,
                    "wind_speed": 0.15,
                },
                "narrative": "Pre-monsoon showers wet the Himalayan slopes. Nothing unusual. Soil is absorbing moisture at normal seasonal rates.",
            },
            {
                "date": "2015-04-22",
                "day_label": "April 22 – Slopes are damp, seismic quiet",
                "conditions": {
                    "rainfall_intensity": 0.35,
                    "soil_saturation": 0.50,
                    "quake_magnitude": 0.10,
                    "temperature_anomaly": 0.15,
                    "precipitation_deficit": 0.0,
                    "vegetation_dryness": 0.10,
                    "wind_speed": 0.15,
                },
                "narrative": "Continued light rain. Soil is moderately wet. Minor micro-seismic activity (normal for the region). CascadeWatch notes the combination but risk is LOW.",
            },
            {
                "date": "2015-04-25",
                "day_label": "April 25 – M7.8 Earthquake strikes",
                "conditions": {
                    "rainfall_intensity": 0.30,
                    "soil_saturation": 0.55,
                    "quake_magnitude": 0.95,
                    "temperature_anomaly": 0.15,
                    "precipitation_deficit": 0.0,
                    "vegetation_dryness": 0.10,
                    "wind_speed": 0.10,
                },
                "narrative": "A magnitude 7.8 earthquake strikes near Gorkha. Massive destruction from the quake itself. CascadeWatch IMMEDIATELY fires a CRITICAL cascade alert: M7.8 on wet, steep, deforested slopes = imminent large-scale landslides. It also flags rivers may be dammed by debris, creating delayed flood risk.",
            },
            {
                "date": "2015-04-27",
                "day_label": "April 27 – Landslides begin",
                "conditions": {
                    "rainfall_intensity": 0.40,
                    "soil_saturation": 0.65,
                    "quake_magnitude": 0.60,
                    "temperature_anomaly": 0.15,
                    "precipitation_deficit": 0.0,
                    "vegetation_dryness": 0.10,
                    "wind_speed": 0.20,
                },
                "narrative": "Hundreds of landslides triggered across central Nepal. Aftershocks continue destabilising slopes. Rain resumes. Debris dams form on at least 5 rivers. CascadeWatch extends alert: flood risk downstream of debris dams.",
            },
            {
                "date": "2015-05-12",
                "day_label": "May 12 – M7.3 aftershock compounds",
                "conditions": {
                    "rainfall_intensity": 0.45,
                    "soil_saturation": 0.70,
                    "quake_magnitude": 0.85,
                    "temperature_anomaly": 0.20,
                    "precipitation_deficit": 0.0,
                    "vegetation_dryness": 0.10,
                    "wind_speed": 0.20,
                },
                "narrative": "A M7.3 aftershock hits. More landslides. Some debris dams breach, causing flash floods downstream. The cascade chain extends: earthquake → landslides → river damming → delayed flash floods. CascadeWatch had flagged all of this on April 25.",
            },
        ],
    },
}

# ---------------------------------------------------------------------------
# LIVE DATA FETCHERS
# ---------------------------------------------------------------------------

HTTP_CLIENT: Optional[httpx.AsyncClient] = None


async def get_client() -> httpx.AsyncClient:
    global HTTP_CLIENT
    if HTTP_CLIENT is None or HTTP_CLIENT.is_closed:
        HTTP_CLIENT = httpx.AsyncClient(timeout=15.0)
    return HTTP_CLIENT


async def fetch_usgs_earthquakes(
    min_magnitude: float = 2.5,
    days_back: int = 7,
    limit: int = 50,
) -> list[dict]:
    """Fetch recent earthquakes from USGS."""
    client = await get_client()
    end = datetime.utcnow()
    start = end - timedelta(days=days_back)
    url = "https://earthquake.usgs.gov/fdsnws/event/1/query"
    params = {
        "format": "geojson",
        "starttime": start.strftime("%Y-%m-%d"),
        "endtime": end.strftime("%Y-%m-%d"),
        "minmagnitude": min_magnitude,
        "limit": limit,
        "orderby": "time",
    }
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        data = resp.json()
        results = []
        for f in data.get("features", []):
            props = f["properties"]
            coords = f["geometry"]["coordinates"]
            results.append({
                "id": f["id"],
                "magnitude": props["mag"],
                "place": props["place"],
                "time": props["time"],
                "depth_km": coords[2],
                "lat": coords[1],
                "lon": coords[0],
                "url": props.get("url", ""),
            })
        return results
    except Exception as e:
        return [{"error": str(e)}]


async def fetch_weather(lat: float, lon: float) -> dict:
    """Fetch current + 7-day weather from Open-Meteo (free, no key)."""
    client = await get_client()
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
        "timezone": "auto",
        "forecast_days": 7,
    }
    try:
        resp = await client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# CASCADE SCORING ENGINE — the brain
# ---------------------------------------------------------------------------


def normalize_magnitude(mag: float) -> float:
    """Normalize earthquake magnitude (0-10 scale) to 0-1."""
    if mag <= 0:
        return 0.0
    return min(mag / 9.0, 1.0)


def normalize_rainfall(precip_mm: float) -> float:
    """Normalize daily precipitation (mm) to 0-1. >100mm = extreme."""
    return min(precip_mm / 100.0, 1.0)


def normalize_soil_saturation(humidity: float, precip_7day: float) -> float:
    """Estimate soil saturation from humidity + cumulative precipitation."""
    humidity_factor = humidity / 100.0
    precip_factor = min(precip_7day / 200.0, 1.0)
    return min((humidity_factor * 0.4 + precip_factor * 0.6), 1.0)


def compute_cascade_risk(
    pattern: dict,
    region: dict,
    conditions: dict,
) -> dict:
    """Compute cascade risk score for a pattern in a region given conditions."""
    factor_scores = {}
    for factor in pattern["factors"]:
        name = factor["name"]
        weight = factor["weight"]

        # Map factor to a value from conditions or region profile
        if name == "quake_magnitude":
            raw = conditions.get("quake_magnitude", 0.0)
        elif name == "slope_steepness":
            raw = region.get("slope_steepness", 0.0)
        elif name == "soil_saturation":
            raw = conditions.get("soil_saturation", 0.0)
        elif name == "deforestation":
            raw = region.get("deforestation", 0.0)
        elif name == "historical_precedent":
            raw = region.get("historical_precedent", 0.0)
        elif name == "rainfall_intensity":
            raw = conditions.get("rainfall_intensity", 0.0)
        elif name == "elevation_risk":
            raw = region.get("elevation_risk", 0.0)
        elif name == "dam_proximity":
            raw = region.get("dam_proximity", 0.0)
        elif name == "drainage_landcover":
            raw = region.get("drainage_landcover", 0.0)
        elif name == "quake_depth_shallow":
            depth = conditions.get("quake_depth_km", 100)
            raw = max(0, 1.0 - (depth / 70.0))  # shallower = higher risk
        elif name == "ocean_floor":
            raw = region.get("ocean_floor", 0.0)
        elif name == "coastal_population":
            raw = region.get("coastal_population", 0.0)
        elif name == "temperature_anomaly":
            raw = conditions.get("temperature_anomaly", 0.0)
        elif name == "precipitation_deficit":
            raw = conditions.get("precipitation_deficit", 0.0)
        elif name == "vegetation_dryness":
            raw = conditions.get("vegetation_dryness", 0.0)
        elif name == "wind_speed":
            raw = conditions.get("wind_speed", 0.0)
        else:
            raw = 0.0

        score = min(max(raw, 0.0), 1.0)
        factor_scores[name] = {
            "label": factor["label"],
            "value": round(score, 3),
            "weight": weight,
            "weighted": round(score * weight, 3),
        }

    total_score = sum(f["weighted"] for f in factor_scores.values())
    threshold = pattern["threshold"]

    if total_score >= threshold + 0.15:
        level = "CRITICAL"
    elif total_score >= threshold:
        level = "HIGH"
    elif total_score >= threshold - 0.15:
        level = "MODERATE"
    else:
        level = "LOW"

    return {
        "pattern_id": pattern["id"],
        "pattern_name": pattern["name"],
        "chain": pattern["chain"],
        "description": pattern["description"],
        "score": round(total_score, 3),
        "threshold": threshold,
        "level": level,
        "factors": factor_scores,
    }


def build_conditions_from_weather(weather: dict, quake_mag: float = 0.0, quake_depth: float = 100.0) -> dict:
    """Convert Open-Meteo weather response into condition values."""
    current = weather.get("current", {})
    daily = weather.get("daily", {})

    precip_now = current.get("precipitation", 0)
    humidity = current.get("relative_humidity_2m", 50)
    wind = current.get("wind_speed_10m", 0)
    temp = current.get("temperature_2m", 25)

    # 7-day cumulative precip
    precip_7day = sum(daily.get("precipitation_sum", [0]) or [0])

    return {
        "rainfall_intensity": normalize_rainfall(precip_now),
        "soil_saturation": normalize_soil_saturation(humidity, precip_7day),
        "quake_magnitude": normalize_magnitude(quake_mag),
        "quake_depth_km": quake_depth,
        "temperature_anomaly": min(max((temp - 35) / 15.0, 0), 1.0),
        "precipitation_deficit": max(0, 1.0 - (precip_7day / 20.0)) if precip_7day < 20 else 0.0,
        "vegetation_dryness": max(0, 1.0 - humidity / 100.0),
        "wind_speed": min(wind / 80.0, 1.0),
    }


# ---------------------------------------------------------------------------
# API ENDPOINTS
# ---------------------------------------------------------------------------


@app.get("/")
async def serve_frontend():
    return FileResponse("/home/user/cascadewatch/static/index.html")


@app.get("/api/regions")
async def get_regions():
    """List all monitored regions."""
    return [
        {
            "id": r["id"],
            "name": r["name"],
            "lat": r["lat"],
            "lon": r["lon"],
            "description": r["description"],
        }
        for r in REGIONS
    ]


@app.get("/api/earthquakes/recent")
async def get_recent_earthquakes(
    min_mag: float = Query(2.5),
    days: int = Query(7),
):
    """Fetch recent earthquakes from USGS."""
    return await fetch_usgs_earthquakes(min_magnitude=min_mag, days_back=days)


@app.get("/api/regions/{region_id}/risk")
async def get_region_risk(region_id: str):
    """Compute live cascade risk for a region using real-time data."""
    region = REGION_MAP.get(region_id)
    if not region:
        return JSONResponse({"error": "Region not found"}, status_code=404)

    # Fetch live weather
    weather = await fetch_weather(region["lat"], region["lon"])

    # Check for recent earthquakes near this region
    quakes = await fetch_usgs_earthquakes(min_magnitude=2.0, days_back=7)
    nearest_mag = 0.0
    nearest_depth = 100.0
    for q in quakes:
        if "error" in q:
            continue
        dist = math.sqrt((q["lat"] - region["lat"]) ** 2 + (q["lon"] - region["lon"]) ** 2)
        if dist < 5.0 and q["magnitude"] > nearest_mag:
            nearest_mag = q["magnitude"]
            nearest_depth = q["depth_km"]

    conditions = build_conditions_from_weather(weather, nearest_mag, nearest_depth)

    # Score ALL cascade patterns for this region
    risks = []
    for pattern in CASCADE_PATTERNS:
        risk = compute_cascade_risk(pattern, region, conditions)
        risks.append(risk)

    risks.sort(key=lambda r: r["score"], reverse=True)

    return {
        "region": {
            "id": region["id"],
            "name": region["name"],
            "lat": region["lat"],
            "lon": region["lon"],
        },
        "conditions": conditions,
        "cascade_risks": risks,
        "highest_level": risks[0]["level"] if risks else "LOW",
        "highest_score": risks[0]["score"] if risks else 0,
        "timestamp": datetime.utcnow().isoformat(),
    }


@app.get("/api/replay/events")
async def list_replay_events():
    """List available historical replay events."""
    return [
        {
            "id": eid,
            "name": ev["name"],
            "region_id": ev["region_id"],
            "summary": ev["summary"],
            "death_toll": ev["death_toll"],
            "steps": len(ev["timeline"]),
        }
        for eid, ev in REPLAY_EVENTS.items()
    ]


@app.get("/api/replay/{event_id}")
async def replay_event(event_id: str):
    """Replay a historical cascade event step by step with scoring."""
    event = REPLAY_EVENTS.get(event_id)
    if not event:
        return JSONResponse({"error": "Event not found"}, status_code=404)

    region = REGION_MAP.get(event["region_id"])
    if not region:
        return JSONResponse({"error": "Region not found"}, status_code=404)

    steps = []
    for step in event["timeline"]:
        conditions = step["conditions"]
        risks = []
        for pattern in CASCADE_PATTERNS:
            risk = compute_cascade_risk(pattern, region, conditions)
            risks.append(risk)
        risks.sort(key=lambda r: r["score"], reverse=True)

        steps.append({
            "date": step["date"],
            "day_label": step["day_label"],
            "narrative": step["narrative"],
            "conditions": conditions,
            "cascade_risks": risks,
            "highest_level": risks[0]["level"],
            "highest_score": risks[0]["score"],
        })

    return {
        "event_id": event_id,
        "name": event["name"],
        "region": {
            "id": region["id"],
            "name": region["name"],
            "lat": region["lat"],
            "lon": region["lon"],
        },
        "summary": event["summary"],
        "death_toll": event["death_toll"],
        "steps": steps,
    }


@app.get("/api/patterns")
async def get_patterns():
    """List all cascade patterns."""
    return CASCADE_PATTERNS


# Serve static files
app.mount("/static", StaticFiles(directory="/home/user/cascadewatch/static"), name="static")

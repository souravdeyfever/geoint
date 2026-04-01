import dash
from dash import dcc, html, dash_table, Input, Output, State, ALL
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import numpy as np
import os
import json
import sqlite3
import random
import urllib.request
import base64
import xml.etree.ElementTree as ET
from urllib.error import URLError, HTTPError
from datetime import datetime, timezone

# Example sample data for Northern Border event clusters
events = pd.DataFrame([
    {"name": "Tawang Sector", "lat": 27.5860, "lon": 91.8655, "type": "Recon / Patrol"},
    {"name": "Chumar Sector", "lat": 32.3430, "lon": 78.3270, "type": "Border Skirmish"},
    {"name": "Pangong Lake", "lat": 33.9416, "lon": 78.2346, "type": "Observation"},
    {"name": "Nubra Valley", "lat": 34.9266, "lon": 77.6150, "type": "Infrastructure"},
    {"name": "Kargil Town", "lat": 34.5557, "lon": 76.1160, "type": "Logistics"},
])

map_fig = px.scatter_map(
    events,
    lat="lat",
    lon="lon",
    hover_name="name",
    hover_data={"type": True, "lat": False, "lon": False},
    color="type",
    zoom=5,
    height=550,
)
map_fig.update_layout(
    mapbox_style="open-street-map",
    mapbox_center={"lat": 32.0, "lon": 78.0},
    margin={"l": 0, "r": 0, "t": 0, "b": 0},
)

weather_points = pd.DataFrame([
    {"site": "Tawang Sector", "lat": 27.5860, "lon": 91.8655, "temperature": 4, "humidity": 72, "wind_kmh": 18, "condition": "Snow / Cold", "forecast": "Snow showers likely", "alert": "Travel advisory in effect"},
    {"site": "Chumar Sector", "lat": 32.3430, "lon": 78.3270, "temperature": 2, "humidity": 68, "wind_kmh": 22, "condition": "Clear / Cold", "forecast": "Strong winds, clear sky", "alert": "High-altitude wind advisory"},
    {"site": "Pangong Lake", "lat": 33.9416, "lon": 78.2346, "temperature": 3, "humidity": 65, "wind_kmh": 20, "condition": "Partly Cloudy", "forecast": "Mountain cloud buildup", "alert": "Reduced visibility overnight"},
    {"site": "Nubra Valley", "lat": 34.9266, "lon": 77.6150, "temperature": 5, "humidity": 58, "wind_kmh": 15, "condition": "Clear", "forecast": "Dry and stable", "alert": "No current alerts"},
    {"site": "Kargil Town", "lat": 34.5557, "lon": 76.1160, "temperature": 6, "humidity": 60, "wind_kmh": 17, "condition": "Breezy", "forecast": "Cold breeze, partly sunny", "alert": "Small craft caution"},
    {"site": "Delhi", "lat": 28.6139, "lon": 77.2090, "temperature": 32, "humidity": 55, "wind_kmh": 10, "condition": "Hazy", "forecast": "Warm with moderate humidity", "alert": "Urban air quality monitoring active"},
])

weather_map_fig = px.scatter_map(
    weather_points,
    lat="lat",
    lon="lon",
    hover_name="site",
    hover_data={"temperature": True, "humidity": True, "wind_kmh": True, "condition": True, "lat": False, "lon": False},
    color="condition",
    size="temperature",
    size_max=18,
    zoom=5,
    height=520,
    custom_data=["site"],
)
weather_map_fig.update_layout(mapbox_style="open-street-map", margin={"t": 40, "l": 0, "r": 0, "b": 0})

weather_point_info = weather_points.set_index("site").to_dict("index")

sector_geo_path = os.path.join(os.path.dirname(__file__), "sector_geo.json")
map_symbols_path = os.path.join(os.path.dirname(__file__), "map_symbols.json")
india_states_geo_path = os.path.join(os.path.dirname(__file__), "INDIA_STATES.geojson")
india_energy_geo_path = os.path.join(os.path.dirname(__file__), "INDIA_ENERGY_PLANTS.geojson")
india_police_geo_path = os.path.join(os.path.dirname(__file__), "INDIA_POLICE_STATIONS.geojson")


def load_json(path):
    if os.path.isfile(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

sector_geo = load_json(sector_geo_path)
map_symbols = load_json(map_symbols_path)
india_states_geo = load_json(india_states_geo_path)
india_energy_geo = load_json(india_energy_geo_path)
india_police_geo = load_json(india_police_geo_path)

DB_PATH = os.path.join(os.path.dirname(__file__), "dashboard_data.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS news_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            source TEXT,
            url TEXT,
            category TEXT,
            updated_at TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS update_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            updated_at TEXT,
            summary TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def persist_news_items(news_items):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM news_cache")
    for item in news_items:
        cursor.execute(
            "INSERT INTO news_cache (title, source, url, category, updated_at) VALUES (?, ?, ?, ?, ?)",
            (item["title"], item["source"], item["url"], item["category"], item["updated_at"]),
        )
    conn.commit()
    conn.close()


def log_update(summary):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO update_log (updated_at, summary) VALUES (?, ?)",
        (datetime.now(timezone.utc).isoformat(), summary),
    )
    conn.commit()
    conn.close()


def current_timestamp():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


NEWS_RSS_FEEDS = [
    {"source": "Reuters World", "url": "https://www.reuters.com/world/rss.xml"},
    {"source": "BBC World", "url": "http://feeds.bbci.co.uk/news/world/rss.xml"},
    {"source": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
]


def get_weather_description(code):
    weather_map = {
        0: "Clear sky",
        1: "Mainly clear",
        2: "Partly cloudy",
        3: "Overcast",
        45: "Fog",
        48: "Depositing rime fog",
        51: "Light drizzle",
        53: "Moderate drizzle",
        55: "Dense drizzle",
        61: "Slight rain",
        63: "Moderate rain",
        65: "Heavy rain",
        71: "Slight snow",
        73: "Moderate snow",
        75: "Heavy snow",
        80: "Rain showers",
        81: "Heavy rain showers",
        82: "Violent rain showers",
    }
    return weather_map.get(code, "Mixed conditions")


def fetch_weather_for_point(lat, lon):
    api_url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}"
        "&current_weather=true&hourly=relativehumidity_2m&timezone=auto"
    )
    request = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=12) as response:
        weather_data = json.loads(response.read().decode())

    current = weather_data.get("current_weather", {})
    humidity = "N/A"
    hourly = weather_data.get("hourly", {})
    humidity_values = hourly.get("relativehumidity_2m", [])
    if humidity_values:
        humidity = int(humidity_values[0])

    return {
        "condition": get_weather_description(int(current.get("weathercode", 0))),
        "temperature": round(float(current.get("temperature", 0)), 1),
        "humidity": humidity,
        "wind_kmh": round(float(current.get("windspeed", 0)), 1),
        "forecast": "Live local weather observed from open-meteo.",
        "alert": "Consult local authorities for operational advisories.",
    }


def refresh_weather_watchpoints():
    global weather_point_info
    for _, row in weather_points.iterrows():
        try:
            weather_point_info[row["site"]] = fetch_weather_for_point(row["lat"], row["lon"])
        except (URLError, HTTPError, ValueError, json.JSONDecodeError):
            continue
    return weather_point_info


def parse_rss_feed(source, feed_url, max_items=2):
    request = urllib.request.Request(feed_url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=10) as response:
        raw_data = response.read()

    root = ET.fromstring(raw_data)
    news_items = []
    for item in root.findall('.//item')[:max_items]:
        title = (item.find('title').text or '').strip() if item.find('title') is not None else ''
        link = (item.find('link').text or '').strip() if item.find('link') is not None else ''
        if title and link:
            news_items.append({
                "title": title,
                "source": source,
                "url": link,
                "category": "Live News",
                "updated_at": current_timestamp(),
            })
    return news_items


def fetch_live_news_items():
    news_items = []
    for feed in NEWS_RSS_FEEDS:
        try:
            news_items.extend(parse_rss_feed(feed["source"], feed["url"], max_items=2))
        except Exception:
            continue

    if len(news_items) < 4:
        return create_sample_news()
    return news_items


def refresh_dashboard_data():
    try:
        news_items = fetch_live_news_items()
    except Exception:
        news_items = create_sample_news()

    if news_items:
        persist_news_items(news_items)
    refresh_weather_watchpoints()
    log_update(f"Dashboard refreshed at {current_timestamp()}")

    return {
        "news_items": news_items,
        "latest_news": news_items,
        "conflict_trend": int(conflict_summary["count"].sum()) if "conflict_summary" in globals() else 0,
        "economic_risk": True,
        "global_signals": global_signals.to_dict("records") if "global_signals" in globals() else [],
    }


def generate_ai_summary(context):
    latest = context.get("latest_news", []) or []
    signals = context.get("global_signals", []) or []
    if isinstance(signals, pd.DataFrame):
        signals = signals.to_dict("records")

    items = []
    if latest:
        items.append(f"{len(latest)} live headlines are currently tracking geopolitical exposure.")
    if any(str(signal.get("Status", "")).lower().startswith("high") for signal in signals):
        items.append("High alert conditions remain active in several monitored theaters.")
    if context.get("conflict_trend", 0) > 20:
        items.append("Conflict pulse is elevated relative to the recent baseline.")
    if any("energy" in item["title"].lower() for item in latest):
        items.append("Energy supply risks remain a primary driver in current reporting.")
    if context.get("economic_risk"):
        items.append("Economic risk signals remain headlined by commodity and logistics pressure.")
    return " ".join(items) or "AI summary generation pending additional data."


def create_sample_news():
    return [
        {
            "title": "Regional security alert expands in South Asia",
            "source": "Reuters",
            "url": "https://www.reuters.com/world/asia-pacific/",
            "category": "Global News",
            "updated_at": current_timestamp(),
        },
        {
            "title": "Energy corridor disruption risk rises",
            "source": "Bloomberg",
            "url": "https://www.bloomberg.com/news/",
            "category": "Economy",
            "updated_at": current_timestamp(),
        },
        {
            "title": "Cyber intelligence teams detect new threat",
            "source": "CNBC",
            "url": "https://www.cnbc.com/",
            "category": "Intelligence",
            "updated_at": current_timestamp(),
        },
    ]


def create_sample_update_data():
    timestamp = current_timestamp()
    news_items = create_sample_news()
    persist_news_items(news_items)
    log_update(f"Dashboard refreshed at {timestamp}")
    return {
        "news_items": news_items,
        "global_signals": [
            {"Category": "Iran Attacks", "Status": "High Alert", "Active Signals": random.randint(70, 110), "Notes": "MENA strike cluster"},
            {"Category": "Military Activity", "Status": "Elevated", "Active Signals": random.randint(60, 90), "Notes": "Airspace and sea lanes"},
            {"Category": "Cyber Threats", "Status": "Monitoring", "Active Signals": random.randint(45, 75), "Notes": "Critical infrastructure risk"},
            {"Category": "Trade Routes", "Status": "Elevated", "Active Signals": random.randint(30, 55), "Notes": "Suez and Hormuz"},
            {"Category": "Climate Anomalies", "Status": "High Alert", "Active Signals": random.randint(50, 70), "Notes": "Extreme weather events"},
        ],
        "conflict_global": [
            {"Date": timestamp.split()[0], "Highlight": "Maritime security incidents in South China Sea", "Region": "Global", "Source": "Reuters", "Link": "https://www.reuters.com/world/"},
            {"Date": timestamp.split()[0], "Highlight": "Border shelling between two Eurasian states", "Region": "Global", "Source": "AFP", "Link": "https://www.afp.com/"},
            {"Date": timestamp.split()[0], "Highlight": "Drone swarm activity over contested desert region", "Region": "Global", "Source": "BBC", "Link": "https://www.bbc.com/"},
            {"Date": timestamp.split()[0], "Highlight": "Clashes around major oil pipeline corridor", "Region": "Global", "Source": "CNBC", "Link": "https://www.cnbc.com/"},
            {"Date": timestamp.split()[0], "Highlight": "New ceasefire breach reports in Africa", "Region": "Global", "Source": "AlJazeera", "Link": "https://www.aljazeera.com/"},
        ],
        "conflict_india": [
            {"Date": timestamp.split()[0], "Highlight": "Increased patrols along LAC sectors", "Region": "India", "Source": "The Hindu", "Link": "https://www.thehindu.com/"},
            {"Date": timestamp.split()[0], "Highlight": "Security alert after multi-state protest", "Region": "India", "Source": "Times of India", "Link": "https://timesofindia.indiatimes.com/"},
            {"Date": timestamp.split()[0], "Highlight": "Counterinsurgency sweep in northeast forest", "Region": "India", "Source": "Indian Express", "Link": "https://indianexpress.com/"},
            {"Date": timestamp.split()[0], "Highlight": "Maritime border exercise in Arabian Sea", "Region": "India", "Source": "Economic Times", "Link": "https://economictimes.indiatimes.com/"},
            {"Date": timestamp.split()[0], "Highlight": "Intelligence report on attempted infiltration", "Region": "India", "Source": "Hindustan Times", "Link": "https://www.hindustantimes.com/"},
        ],
        "global_economy_highlights": [
            "Global PMI expansion continues in major economies.",
            "Energy prices remain elevated amid supply constraints.",
            "Inflation cooling in developed markets but sticky in emerging Asia.",
            "Central banks maintain cautious rate outlook for Q2.",
            "Supply chain recovery is uneven but improving.",
        ],
        "monthly_geo": [
            {"Month": "2026-01", "Standing": "Stable", "Concern": "Energy corridor risks in Europe."},
            {"Month": "2026-02", "Standing": "Elevated", "Concern": "Maritime tensions in Indo-Pacific."},
            {"Month": "2026-03", "Standing": "Watch", "Concern": "Cyber threats to critical systems."},
            {"Month": "2026-04", "Standing": "High", "Concern": "Sanctions spillover affecting supply chains."},
        ],
        "district_news": [
            {"District": "Srinagar", "Headline 1": "Security forces foil infiltration attempt.", "Headline 2": "Road reopening plan announced.", "Headline 3": "Local protests over administrative changes."},
            {"District": "Leh", "Headline 1": "Tourism restrictions eased for summer season.", "Headline 2": "Weather alert issued for flash floods.", "Headline 3": "Border patrols reinforce high-altitude posts."},
            {"District": "Mumbai", "Headline 1": "Maritime security exercise launched.", "Headline 2": "Cyber hygiene advisory for financial firms.", "Headline 3": "Police department launches community outreach."},
        ],
        "security_highlights": [
            "Army intelligence flags cross-border artillery escalation.",
            "Internal security focus on counterterrorism in eastern states.",
            "Police mobilization ahead of major national event.",
            "Border security operations increase along northern frontier.",
        ],
        "osint_trend": pd.DataFrame({
            "date": pd.date_range(end=pd.Timestamp.now(), periods=10, freq="D"),
            "event_count": [random.randint(20, 40) for _ in range(10)],
        }),
        "conflict_event_mix": pd.DataFrame({
            "event_type": ["Skirmish", "Patrol", "Observation", "Infrastructure", "Diplomatic"],
            "count": [random.randint(5, 18) for _ in range(5)],
        }),
        "daily_geo_scenario": f"{timestamp}: National burden remains high with simultaneous diplomatic and security pressures.",
    }


sector_geo = load_json(sector_geo_path)
map_symbols = load_json(map_symbols_path)
india_states_geo = load_json(india_states_geo_path)
india_energy_geo = load_json(india_energy_geo_path)
india_police_geo = load_json(india_police_geo_path)


def extract_polygons(geometry):
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates", [])
    if geom_type == "Polygon":
        return [coords]
    if geom_type == "MultiPolygon":
        return coords
    return []

repo_map_fig = go.Figure()

state_drawn = False
if sector_geo is not None:
    for feature in sector_geo.get("features", []):
        props = feature.get("properties", {})
        name = props.get("name") or props.get("sector") or "Sector"
        sector = props.get("sector") or "Unknown"
        threat = props.get("threat") or "N/A"
        for polygon in extract_polygons(feature["geometry"]):
            for ring in polygon:
                lons = [point[0] for point in ring]
                lats = [point[1] for point in ring]
                repo_map_fig.add_trace(go.Scattermap(
                    lon=lons,
                    lat=lats,
                    mode="lines",
                    fill="toself",
                    fillcolor="rgba(0, 123, 255, 0.12)",
                    line=dict(color="rgba(0, 123, 255, 0.8)", width=2),
                    name=f"{sector} Area" if not state_drawn else "",
                    legendgroup="Sector Area",
                    showlegend=not state_drawn,
                    hoverinfo="text",
                    text=f"{name} — {sector} — Threat: {threat}",
                ))
                state_drawn = True

symbol_map = {}
if map_symbols is not None:
    for category in map_symbols.get("categories", []):
        symbol_map[category.get("label")] = category

energy_lons = []
energy_lats = []
energy_text = []
if india_energy_geo:
    for feature in india_energy_geo.get("features", []):
        geom = feature.get("geometry", {})
        props = feature.get("properties", {})
        if geom.get("type") == "Point":
            lon, lat = geom.get("coordinates", [None, None])
            energy_lons.append(lon)
            energy_lats.append(lat)
            energy_text.append(props.get("name", "Energy Plant"))

if energy_lons:
    repo_map_fig.add_trace(go.Scattermap(
        lon=energy_lons,
        lat=energy_lats,
        mode="markers",
        marker=dict(size=10, color="#ffcc00", symbol="star"),
        name="Energy Plant",
        legendgroup="Energy Plant",
        text=energy_text,
        hoverinfo="text",
    ))

police_lons = []
police_lats = []
police_text = []
if india_police_geo:
    for feature in india_police_geo.get("features", []):
        geom = feature.get("geometry", {})
        props = feature.get("properties", {})
        if geom.get("type") == "Point":
            lon, lat = geom.get("coordinates", [None, None])
            police_lons.append(lon)
            police_lats.append(lat)
            police_text.append(props.get("name", "Police Station"))

if police_lons:
    repo_map_fig.add_trace(go.Scattermap(
        lon=police_lons,
        lat=police_lats,
        mode="markers",
        marker=dict(size=8, color="#1f77b4", symbol="circle"),
        name="Police Station",
        legendgroup="Police Station",
        text=police_text,
        hoverinfo="text",
    ))

if sector_geo is None and not (india_states_geo or india_energy_geo or india_police_geo):
    repo_map_fig.add_annotation(
        text="sector_geo.json and map_symbols.json are not available, and requested INDIA_*.geojson files are missing.",
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(size=16, color="#444"),
    )
    repo_map_fig.update_layout(mapbox_style="open-street-map", mapbox_center={"lat": 22.0, "lon": 80.0}, mapbox_zoom=4)
else:
    repo_map_fig.update_layout(
        mapbox_style="open-street-map",
        mapbox_center={"lat": 22.0, "lon": 80.0},
        mapbox_zoom=4,
        margin={"t": 40, "l": 0, "r": 0, "b": 0},
        legend=dict(title="India GeoJSON Layers", orientation="h", y=1.05, x=0),
    )

osint_trend = pd.DataFrame({
    "date": pd.date_range(start="2026-03-15", periods=10, freq="D"),
    "event_count": [12, 18, 21, 15, 25, 29, 34, 28, 31, 26],
})

conflict_summary = pd.DataFrame({
    "event_type": ["Skirmish", "Patrol", "Observation", "Infrastructure", "Diplomatic"],
    "count": [14, 10, 8, 7, 5],
})

conflict_event_definitions = {
    "Skirmish": "Short-range armed clashes and patrol exchanges in contested border sectors.",
    "Patrol": "Security or reconnaissance movements that indicate increased operational tempo.",
    "Observation": "Surveillance and intelligence-gathering activity around strategic sites.",
    "Infrastructure": "Logistics, road convoy, and base support activity tied to conflict operations.",
    "Diplomatic": "State-level maneuvers, statements, and sanctions that influence the conflict environment.",
}

fire_hotspots = pd.DataFrame([
    {"site": "Eastern Ladakh", "lat": 34.5, "lon": 78.4, "confidence": 0.88},
    {"site": "Upper Arunachal", "lat": 28.7, "lon": 94.8, "confidence": 0.76},
    {"site": "Western Sikkim", "lat": 27.1, "lon": 88.7, "confidence": 0.69},
])

power_climate = pd.DataFrame({
    "date": pd.date_range(start="2026-03-15", periods=10, freq="D"),
    "solar_index": [55, 62, 58, 65, 70, 68, 72, 69, 75, 78],
    "precipitation": [4.1, 3.8, 4.0, 2.9, 2.5, 3.2, 1.8, 2.0, 2.3, 1.5],
})

global_signals = pd.DataFrame([
    {"Category": "Iran Attacks", "Status": "High Alert", "Active Signals": 93, "Notes": "MENA strike cluster", "Source": "Reuters"},
    {"Category": "Military Activity", "Status": "Elevated", "Active Signals": 78, "Notes": "Airspace and sea lanes", "Source": "Jane's Defence"},
    {"Category": "Cyber Threats", "Status": "Monitoring", "Active Signals": 62, "Notes": "Critical infrastructure risk", "Source": "CyberScoop"},
    {"Category": "Nuclear Sites", "Status": "Monitoring", "Active Signals": 31, "Notes": "Facility watchlist", "Source": "World Nuclear News"},
    {"Category": "Trade Routes", "Status": "Elevated", "Active Signals": 44, "Notes": "Suez and Hormuz", "Source": "Bloomberg"},
    {"Category": "Climate Anomalies", "Status": "High Alert", "Active Signals": 59, "Notes": "Extreme weather events", "Source": "BBC"},
])

init_db()
refresh_dashboard_data()

live_news_sources = [
    "Bloomberg",
    "SkyNews",
    "Euronews",
    "DW",
    "CNBC",
    "CNN",
    "France 24",
    "AlArabiya",
    "AlJazeera",
]

ai_insights = [
    "AI Strategic Posture: Elevated tension in Eurasia corridors.",
    "Market impact risk is highest for energy and precious metals.",
    "Infrastructure cascade risk remains medium in contested zones.",
]

# Daily conflict highlights for the last 10 days
conflict_dates = pd.date_range(end=pd.Timestamp.today(), periods=10)
conflict_global = pd.DataFrame({
    "Date": conflict_dates.strftime("%Y-%m-%d"),
    "Highlight": [
        "Maritime security incidents in South China Sea",
        "Border shelling between two Eurasian states",
        "Drone swarm activity over contested desert region",
        "Clashes around major oil pipeline corridor",
        "New ceasefire breach reports in Africa",
        "Proxy forces mobilize along frontier",
        "Cyber attack attributed to state-aligned group",
        "Arms convoy interdicted near disputed island",
        "Militia buildup reported in coastal region",
        "Bomb threat forced evacuation at rail hub",
    ],
    "Region": ["Global"] * 10,
    "Source": [
        "Reuters",
        "AFP",
        "BBC",
        "Bloomberg",
        "Al Jazeera",
        "CNN",
        "The Guardian",
        "Reuters",
        "Associated Press",
        "Times of India",
    ],
    "Link": [
        "https://www.reuters.com/world/",
        "https://www.afp.com/",
        "https://www.bbc.com/news/world",
        "https://www.bloomberg.com/",
        "https://www.aljazeera.com/",
        "https://edition.cnn.com/",
        "https://www.theguardian.com/world",
        "https://www.reuters.com/world/",
        "https://apnews.com/",
        "https://timesofindia.indiatimes.com/",
    ],
})
conflict_india = pd.DataFrame({
    "Date": conflict_dates.strftime("%Y-%m-%d"),
    "Highlight": [
        "Increased patrols along LAC sectors",
        "Security alert after multi-state protest",
        "Counterinsurgency sweep in northeast forest",
        "Maritime border exercise in Arabian Sea",
        "Intelligence report on attempted infiltration",
        "Rapid response to railway sabotage attempt",
        "Armed strike in border district",
        "Joint security drill near western border",
        "Airspace surveillance intensified over Kashmir",
        "Cyber resilience alert for critical infrastructure",
    ],
    "Region": ["India"] * 10,
    "Source": [
        "The Hindu",
        "Times of India",
        "Indian Express",
        "Economic Times",
        "Hindustan Times",
        "NDTV",
        "PTI",
        "The Tribune",
        "Hindustan Times",
        "Business Standard",
    ],
    "Link": [
        "https://www.thehindu.com/news/national/",
        "https://timesofindia.indiatimes.com/",
        "https://indianexpress.com/",
        "https://economictimes.indiatimes.com/",
        "https://www.hindustantimes.com/",
        "https://www.ndtv.com/",
        "https://www.ptinews.com/",
        "https://www.tribuneindia.com/",
        "https://www.hindustantimes.com/",
        "https://www.business-standard.com/",
    ],
})

# Historical currency trends for top 10 countries with INR baseline
currency_list = ["INR", "USD", "EUR", "JPY", "GBP", "CNY", "AUD", "CAD", "CHF", "SGD"]
years = np.arange(2016, 2026)
currency_history = []
for i, currency in enumerate(currency_list):
    base = 1.0 + i * 0.18
    trend = np.linspace(base, base + 2.5 + i * 0.2, len(years))
    cycle = np.sin(np.linspace(0, 6 * np.pi, len(years))) * (0.12 + i * 0.01)
    values = np.abs(trend + cycle)
    currency_history.append(pd.DataFrame({
        "Year": years,
        "Currency": currency,
        "Index": values,
    }))
currency_history = pd.concat(currency_history, ignore_index=True)

currency_chart = px.line(
    currency_history,
    x="Year",
    y="Index",
    color="Currency",
    title="Top 10 Currency Trajectories vs INR (10-year view)",
    labels={"Index": "Relative Index", "Year": "Year"},
    height=520,
)

price_dates = pd.date_range(end=pd.Timestamp.today(), periods=7, freq="D")
price_trends = pd.DataFrame({
    "Date": price_dates.strftime("%Y-%m-%d"),
    "INR per USD": np.round(np.linspace(82.5, 83.7, 7) + np.random.randn(7) * 0.08, 2),
    "Delhi Petrol Price": np.round(np.linspace(110, 114, 7) + np.random.randn(7) * 0.5, 2),
    "Brent Crude (USD)": np.round(np.linspace(78, 82, 7) + np.random.randn(7) * 0.4, 2),
})
price_graph = px.line(
    price_trends,
    x="Date",
    y=["INR per USD", "Delhi Petrol Price", "Brent Crude (USD)"],
    title="Last 7 Days: INR, Petrol Delhi, Raw Petroleum Price",
    labels={"value": "Price", "variable": "Series"},
    height=420,
)

stock_dates = pd.date_range(end=pd.Timestamp.today(), periods=60, freq="D")
stock_market_data = pd.DataFrame({
    "Date": np.tile(stock_dates, 3),
    "Index": np.concatenate([
        np.linspace(4200, 4600, len(stock_dates)) + np.random.randn(len(stock_dates)) * 20,
        np.linspace(15000, 16300, len(stock_dates)) + np.random.randn(len(stock_dates)) * 50,
        np.linspace(3900, 4300, len(stock_dates)) + np.random.randn(len(stock_dates)) * 30,
    ]),
    "Market": ["S&P 500"] * len(stock_dates) + ["Nifty 50"] * len(stock_dates) + ["Sensex"] * len(stock_dates),
})
stock_market_fig = px.line(
    stock_market_data,
    x="Date",
    y="Index",
    color="Market",
    title="Global and National Stock Market Trends",
    labels={"Index": "Index Level", "Date": "Date"},
    height=520,
)

# Global economy highlights
global_economy_highlights = [
    {
        "Headline": "Global PMI expansion continues in major economies.",
        "Source": "Bloomberg",
        "Link": "https://www.bloomberg.com/economics",
    },
    {
        "Headline": "Energy prices remain elevated amid supply constraints.",
        "Source": "Reuters",
        "Link": "https://www.reuters.com/business/energy/",
    },
    {
        "Headline": "Inflation cooling in developed markets but sticky in emerging Asia.",
        "Source": "Financial Times",
        "Link": "https://www.ft.com/global-economy",
    },
    {
        "Headline": "Central banks maintain cautious rate outlook for Q2.",
        "Source": "The Wall Street Journal",
        "Link": "https://www.wsj.com/news/economy",
    },
    {
        "Headline": "Supply chain recovery is uneven but improving.",
        "Source": "OECD",
        "Link": "https://www.oecd.org/asia-pacific/",
    },
]

# Daily top 3 district news highlights for India (sample)
district_news = pd.DataFrame([
    {
        "District": "Srinagar",
        "Headline": "Security forces foil infiltration attempt along Srinagar corridor.",
        "Source": "The Hindu",
        "Link": "https://www.thehindu.com/news/national/",
    },
    {
        "District": "Leh",
        "Headline": "Weather advisory issued for flash floods in Ladakh.",
        "Source": "Times of India",
        "Link": "https://timesofindia.indiatimes.com/india",
    },
    {
        "District": "Mumbai",
        "Headline": "Maritime security exercise launched off Mumbai coast.",
        "Source": "Hindustan Times",
        "Link": "https://www.hindustantimes.com/india-news",
    },
    {
        "District": "Delhi",
        "Headline": "New intelligence centre opens in the capital.",
        "Source": "Indian Express",
        "Link": "https://indianexpress.com/section/india/",
    },
    {
        "District": "Guwahati",
        "Headline": "Counter-insurgency operation secures northeastern border route.",
        "Source": "The Hindu",
        "Link": "https://www.thehindu.com/news/national/other-states/",
    },
])

# Security and national concern highlights
security_highlights = [
    {
        "Headline": "Army intelligence flags cross-border artillery escalation.",
        "Source": "NDTV",
        "Link": "https://www.ndtv.com/india",
    },
    {
        "Headline": "Internal security focus on counterterrorism in eastern states.",
        "Source": "Indian Express",
        "Link": "https://indianexpress.com/section/india/",
    },
    {
        "Headline": "Police mobilization ahead of major national event.",
        "Source": "Times of India",
        "Link": "https://timesofindia.indiatimes.com/india",
    },
    {
        "Headline": "Border security operations increase along northern frontier.",
        "Source": "Hindustan Times",
        "Link": "https://www.hindustantimes.com/india-news",
    },
    {
        "Headline": "Threat assessments updated for cyber critical infrastructure.",
        "Source": "Economic Times",
        "Link": "https://economictimes.indiatimes.com/news/defence",
    },
    {
        "Headline": "National security review scheduled for strategic command.",
        "Source": "The Hindu",
        "Link": "https://www.thehindu.com/news/national/",
    },
]

# Monthly global geopolitical standings
geo_monthly_standings = pd.DataFrame([
    {"Month": "2026-01", "Standing": "Stable", "Concern": "Energy corridor risks in Europe.", "Source": "Reuters", "Link": "https://www.reuters.com/world/"},
    {"Month": "2026-02", "Standing": "Elevated", "Concern": "Maritime tensions in Indo-Pacific.", "Source": "Bloomberg", "Link": "https://www.bloomberg.com/world"},
    {"Month": "2026-03", "Standing": "Watch", "Concern": "Cyber threats to critical systems.", "Source": "BBC", "Link": "https://www.bbc.com/news/technology"},
    {"Month": "2026-04", "Standing": "High", "Concern": "Sanctions spillover affecting supply chains.", "Source": "CNBC", "Link": "https://www.cnbc.com/world/"},
])

# YouTube live footage feeds
youtube_live_streams = [
    {"title": "Live Feed 1", "embed": "https://www.youtube.com/embed/qy4i1kw1HFs", "source": "YouTube"},
    {"title": "Live Feed 2", "embed": "https://www.youtube.com/embed/aVJ7fDqPjvQ", "source": "YouTube"},
    {"title": "Live Feed 3", "embed": "https://www.youtube.com/embed/q1lRwezhTIE", "source": "YouTube"},
    {"title": "Live Feed 4", "embed": "https://www.youtube.com/embed/vYRfQo6JMxc", "source": "YouTube"},
    {"title": "Live Feed 5", "embed": "https://www.youtube.com/embed/KG5pfOFpm2Y", "source": "YouTube"},
    {"title": "Live Feed 6", "embed": "https://www.youtube.com/embed/UDAZWxehMAI", "source": "YouTube"},
    {"title": "Live Feed 7", "embed": "https://www.youtube.com/embed/vhpCErLQBgg", "source": "YouTube"},
    {"title": "Live Feed 8", "embed": "https://www.youtube.com/embed/gmtlJ_m2r5A", "source": "YouTube"},
]

# Terrorism historical incident dataset (sample from provided data)
terrorism_events = pd.DataFrame([
    {"Year": 1947, "Date": "01-09-1947", "Event": "Noakhali Riots", "Description": "Violence during Partition with mass killings", "Location": "Noakhali", "State": "Bengal", "Deaths": "500+", "Injuries": "1000+", "Lat": 23.0738, "Lon": 90.9808, "Status": "Unresolved", "Convictions": "Unknown", "Group": "Communal mobs"},
    {"Year": 1948, "Date": "30-01-1948", "Event": "Gandhi Assassination", "Description": "Assassination of Mahatma Gandhi", "Location": "Birla House", "State": "Delhi", "Deaths": "1", "Injuries": "0", "Lat": 28.6139, "Lon": 77.2090, "Status": "Godse executed", "Convictions": "3", "Group": "Hindu extremists"},
    {"Year": 1975, "Date": "09-12-1975", "Event": "Delhi Bus Bombing", "Description": "Bomb exploded on city bus", "Location": "Delhi", "State": "Delhi", "Deaths": "9", "Injuries": "21", "Lat": 28.6139, "Lon": 77.2090, "Status": "Unresolved", "Convictions": "Unknown", "Group": "Unknown"},
    {"Year": 1984, "Date": "03-11-1984", "Event": "Anti-Sikh Riots", "Description": "Mass violence targeting Sikh community", "Location": "Delhi", "State": "Delhi", "Deaths": "3000+", "Injuries": "Unknown", "Lat": 28.7041, "Lon": 77.1025, "Status": "Unresolved", "Convictions": "Unknown", "Group": "Mob violence"},
    {"Year": 1991, "Date": "21-05-1991", "Event": "Rajiv Gandhi Assassination", "Description": "Liberation Tigers suicide bombing at rally", "Location": "Sriperumbudur", "State": "Tamil Nadu", "Deaths": "18", "Injuries": "45", "Lat": 12.9675, "Lon": 79.9495, "Status": "Accused convicted", "Convictions": "9", "Group": "LTTE"},
    {"Year": 1993, "Date": "16-03-1993", "Event": "Bowbazar Bombing", "Description": "Explosion in Bowbazar club", "Location": "Bowbazar", "State": "Kolkata", "Deaths": "69", "Injuries": "Unknown", "Lat": 22.5726, "Lon": 88.3639, "Status": "6 convicted", "Convictions": "6", "Group": "Rashid Khan Group"},
    {"Year": 1996, "Date": "21-05-1996", "Event": "Lajpat Nagar Blasts", "Description": "Serial bombings in market", "Location": "Lajpat Nagar", "State": "Delhi", "Deaths": "13", "Injuries": "39", "Lat": 28.5630, "Lon": 77.2432, "Status": "Convicted", "Convictions": "5", "Group": "Babbar Khalsa"},
    {"Year": 2001, "Date": "13-12-2001", "Event": "Parliament Attack", "Description": "Suicide squad stormed Parliament complex", "Location": "New Delhi", "State": "Delhi", "Deaths": "9", "Injuries": "18", "Lat": 28.6174, "Lon": 77.2082, "Status": "4 convicted (2002)", "Convictions": "5", "Group": "Jaish-e-Mohammed"},
    {"Year": 2002, "Date": "24-09-2002", "Event": "Akshardham Temple Attack", "Description": "Militants stormed Gujarat temple", "Location": "Gandhinagar", "State": "Gujarat", "Deaths": "33", "Injuries": "80", "Lat": 23.2156, "Lon": 72.6369, "Status": "2 killed, 1 convicted", "Convictions": "3", "Group": "Lashkar-e-Taiba"},
    {"Year": 2006, "Date": "07-03-2006", "Event": "Varanasi Bombings", "Description": "Triple blasts at temple/rail station", "Location": "Varanasi", "State": "Uttar Pradesh", "Deaths": "23", "Injuries": "101", "Lat": 25.3176, "Lon": 83.0076, "Status": "Convicted", "Convictions": "3", "Group": "Lashkar-e-Taiba"},
    {"Year": 2008, "Date": "26-11-2008", "Event": "Mumbai Attacks (26/11)", "Description": "60-hour siege at multiple locations including Taj Hotel", "Location": "Mumbai", "State": "Maharashtra", "Deaths": "166", "Injuries": "300+", "Lat": 18.9217, "Lon": 72.8332, "Status": "1 executed (2012)", "Convictions": "10", "Group": "Lashkar-e-Taiba"},
    {"Year": 2016, "Date": "06-04-2016", "Event": "Dantewada Maoist Attack", "Description": "Maoists ambushed police convoy", "Location": "Dantewada", "State": "Chhattisgarh", "Deaths": "84", "Injuries": "8", "Lat": 18.9041, "Lon": 81.3506, "Status": "Suppressed", "Convictions": "11", "Group": "CPI-Maoist"},
    {"Year": 2017, "Date": "24-04-2017", "Event": "Sukma Attack", "Description": "Maoists attack on CRPF patrol", "Location": "Sukma", "State": "Chhattisgarh", "Deaths": "26", "Injuries": "8", "Lat": 18.3931, "Lon": 81.8308, "Status": "Ongoing", "Convictions": "Unknown", "Group": "CPI-Maoist"},
    {"Year": 2019, "Date": "14-02-2019", "Event": "Pulwama Attack", "Description": "Suicide bomber rammed CRPF convoy", "Location": "Pulwama", "State": "Jammu & Kashmir", "Deaths": "40", "Injuries": "35", "Lat": 33.8711, "Lon": 74.8995, "Status": "Perpetrator killed", "Convictions": "1", "Group": "Jaish-e-Mohammed"},
    {"Year": 2023, "Date": "27-11-2023", "Event": "Pulwama Firing", "Description": "Militants fired on police convoy", "Location": "Pulwama", "State": "Jammu & Kashmir", "Deaths": "4", "Injuries": "2", "Lat": 33.8711, "Lon": 74.8995, "Status": "Operation ongoing", "Convictions": "4", "Group": "Jaish-e-Mohammed"},
    {"Year": 2024, "Date": "07-03-2024", "Event": "Poonch Attack", "Description": "Terrorists ambushed security forces near LOC", "Location": "Poonch", "State": "Jammu & Kashmir", "Deaths": "5", "Injuries": "6", "Lat": 33.7717, "Lon": 74.0893, "Status": "3 suspects arrested", "Convictions": "3+", "Group": "Jaish-e-Mohammed"},
    {"Year": 2025, "Date": "22-04-2025", "Event": "Pahalgam Tourist Attack", "Description": "Firing on tourist bus by militants", "Location": "Pahalgam", "State": "Jammu & Kashmir", "Deaths": "26", "Injuries": "15", "Lat": 34.0151, "Lon": 75.3185, "Status": "Active operation", "Convictions": "Unknown", "Group": "Lashkar-e-Taiba"},
])
terrorism_events["Deaths_numeric"] = pd.to_numeric(terrorism_events["Deaths"].str.replace(r"\+", "", regex=True).replace({"Unknown": "0", "N/A": "0"}), errors="coerce").fillna(0)
terrorism_events["Injuries_numeric"] = pd.to_numeric(terrorism_events["Injuries"].str.replace(r"\+", "", regex=True).replace({"Unknown": "0", "N/A": "0"}), errors="coerce").fillna(0)

terrorism_map_fig = px.scatter_map(
    terrorism_events,
    lat="Lat",
    lon="Lon",
    hover_name="Event",
    hover_data=["Location", "State", "Status", "Group", "Deaths", "Injuries"],
    custom_data=["Event", "Location", "State", "Group", "Status", "Deaths", "Injuries", "Description"],
    color="Group",
    size="Deaths_numeric",
    size_max=32,
    zoom=4,
    height=520,
    map_style="open-street-map",
    center={"lat": 22.5, "lon": 80.0},
    color_discrete_sequence=px.colors.qualitative.Safe,
    title="India Terrorism Incident Map",
)
terrorism_map_fig.update_traces(marker=dict(opacity=0.85))
terrorism_map_fig.update_layout(margin={"t": 40, "l": 0, "r": 0, "b": 0})

state_group_counts = (
    terrorism_events.groupby(["State", "Group"]).size().reset_index(name="Count")
)
top_group_by_state = (
    state_group_counts.sort_values(["State", "Count"], ascending=[True, False])
    .groupby("State", as_index=False)
    .first()
    .rename(columns={"Group": "Active Group", "Count": "Events"})
)
state_group_summary = top_group_by_state

states = sorted(state_group_summary["State"].unique())
groups = sorted(state_group_summary["Active Group"].unique())
state_positions = {state: (0.1, y) for state, y in zip(states, np.linspace(0.1, 0.9, len(states)))}
group_positions = {group: (0.9, y) for group, y in zip(groups, np.linspace(0.1, 0.9, len(groups)))}

terrorism_network_fig = go.Figure()
for _, row in state_group_summary.iterrows():
    sx, sy = state_positions[row["State"]]
    gx, gy = group_positions[row["Active Group"]]
    terrorism_network_fig.add_trace(go.Scatter(
        x=[sx, gx],
        y=[sy, gy],
        mode="lines",
        line=dict(color="rgba(31,119,180,0.45)", width=2 + row["Events"] / 2),
        hoverinfo="text",
        text=f"{row['State']} → {row['Active Group']}: {row['Events']} incidents",
        showlegend=False,
    ))

terrorism_network_fig.add_trace(go.Scatter(
    x=[state_positions[state][0] for state in states],
    y=[state_positions[state][1] for state in states],
    mode="markers+text",
    marker=dict(size=18, color="#1f77b4"),
    text=states,
    textposition="middle right",
    hoverinfo="text",
    hovertext=[f"State: {state}" for state in states],
    name="State",
))

terrorism_network_fig.add_trace(go.Scatter(
    x=[group_positions[group][0] for group in groups],
    y=[group_positions[group][1] for group in groups],
    mode="markers+text",
    marker=dict(size=18, color="#d62728"),
    text=groups,
    textposition="middle left",
    hoverinfo="text",
    hovertext=[f"Group: {group}" for group in groups],
    name="Perpetrator Group",
))

terrorism_network_fig.update_layout(
    title="State-wise Active Perpetrator Network",
    xaxis=dict(visible=False),
    yaxis=dict(visible=False),
    showlegend=False,
    margin=dict(t=50, l=20, r=20, b=20),
    plot_bgcolor="#f8f9fb",
)

terrorism_details_columns = [
    {"name": label, "id": label}
    for label in ["Year", "Date", "Event", "Location", "State", "Deaths", "Injuries", "Status", "Group"]
]

fire_fig = px.scatter_map(
    fire_hotspots,
    lat="lat",
    lon="lon",
    size="confidence",
    color="confidence",
    hover_name="site",
    title="NASA FIRMS-style Thermal Alerts",
    range_color=[0.6, 0.9],
)
fire_fig.update_layout(
    mapbox_style="open-street-map",
    mapbox_center={"lat": 30.5, "lon": 87.5},
    mapbox_zoom=5,
    margin={"t": 40, "l": 0, "r": 0, "b": 0},
)

open_cctv_streams = [
    {
        "title": "Leh Public Webcam (YouTube)",
        "embed": "https://www.youtube.com/embed/E4JX7pF-1gQ",
        "source": "YouTube"
    },
    {
        "title": "Himachal Hillcam Stream",
        "embed": "https://www.youtube.com/embed/8zZxewJmcEo",
        "source": "YouTube"
    }
]

summary_cards = [
    {"label": "Latest News", "value": "Live feeds & hyperlinked sources", "color": "#2a9d8f"},
    {"label": "Geopolitics", "value": "Global signals and market risk", "color": "#4b8bbe"},
    {"label": "Intelligence", "value": "AI summaries & conflict signals", "color": "#005f73"},
    {"label": "Visualisation", "value": "Geo data, maps and alerts", "color": "#f4a261"},
]

app = dash.Dash(__name__)
app.title = "Security Monitoring — S.I.A Dashboard"

app.layout = html.Div([
    dcc.Store(id="custom-panels-store", storage_type="local"),

    # Header Section
    html.Div([
        html.H1("Security Monitoring — S.I.A Dashboard", style={"margin": "0 0 8px 0"}),
        html.P(
            "A unified monitoring dashboard optimized for national situational awareness with live news, intelligence, conflict feeds, and Gemini AI commentary.",
            style={"margin": "0", "color": "#555", "maxWidth": "720px"},
        ),
        html.P(
            html.A("share your concern with us", href="https://sites.google.com/view/souravdey", target="_blank", style={"color": "#6ec6ff", "textDecoration": "underline"}),
            style={"margin": "8px 0 0 0", "fontSize": "14px", "color": "#aad4ff"},
        ),
    ], style={"textAlign": "center", "padding": "24px", "backgroundColor": "#081a31", "color": "white"}),

    dcc.Interval(id="refresh-interval", interval=3600 * 1000, n_intervals=0),

    html.Div(id="last-updated-banner", style={"padding": "0 24px 12px 24px", "textAlign": "right", "color": "#888", "fontSize": "13px"}),

    # Main Dashboard Grid - Compact 2-3 panels per row
    html.Div([
        # Row 1: Summary Cards (3 cards)
        html.Div([
            html.Div([
                html.H3(card["label"], style={"margin": "0 0 8px 0", "color": "white"}),
                html.P(card["value"], style={"margin": "0", "color": "#d0e7ff"}),
            ], style={"padding": "20px", "backgroundColor": card["color"], "borderRadius": "12px", "textAlign": "center", "boxShadow": "0 4px 12px rgba(0,0,0,0.1)"})
            for card in summary_cards
        ], style={"display": "grid", "gridTemplateColumns": "repeat(3, 1fr)", "gap": "16px", "marginBottom": "24px"}),

        # Row 2: Map and News (2 panels)
        html.Div([
            html.Div([
                html.H2("Live Border Event Map", style={"marginBottom": "16px"}),
                dcc.Graph(figure=map_fig, config={"displayModeBar": False}),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
            html.Div([
                html.H2("Live News & AI Insights", style={"marginBottom": "16px"}),
                html.Div([
                    html.H4("Latest Headlines", style={"marginBottom": "10px"}),
                    html.Ul(id="live-news-list", style={"marginTop": "0", "paddingLeft": "18px"}, children=[html.Li("Loading headlines...")]),
                    html.H4("AI Summary", style={"marginTop": "20px", "marginBottom": "10px"}),
                    html.P(id="ai-summary", style={"marginTop": "0", "lineHeight": "1.8"}, children="AI summary will appear here after refresh."),
                    html.P(id="last-updated-text", style={"marginTop": "18px", "color": "#555", "fontSize": "13px"}, children="Last updated: pending refresh"),
                ], style={"padding": "20px", "backgroundColor": "#f6f9ff", "borderRadius": "16px"}),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
        ], style={"display": "grid", "gridTemplateColumns": "2fr 1fr", "gap": "16px", "marginBottom": "24px"}),

        # Row 3: Global Signals and Currency (2 panels)
        html.Div([
            html.Div([
                html.H2("Global Signals Overview", style={"marginBottom": "16px"}),
                dash_table.DataTable(
                    columns=[
                        {"name": "Category", "id": "Category"},
                        {"name": "Status", "id": "Status"},
                        {"name": "Active Signals", "id": "Active Signals"},
                        {"name": "Notes", "id": "Notes"},
                        {"name": "Source", "id": "Source"},
                    ],
                    data=global_signals.to_dict("records"),
                    style_cell={"textAlign": "left", "padding": "8px", "whiteSpace": "normal", "height": "auto"},
                    style_header={"backgroundColor": "#092d4d", "fontWeight": "bold", "color": "white"},
                    style_data={"backgroundColor": "#fdfdfd", "color": "#111"},
                    style_table={"overflowX": "auto"},
                    page_size=6,
                ),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
            html.Div([
                html.H2("Top 10 Currency Graph vs INR", style={"marginBottom": "16px"}),
                dcc.Graph(figure=currency_chart, config={"displayModeBar": False}),
                html.H2("Last 7 Days: INR, Petrol Delhi, Crude Oil", style={"marginTop": "24px", "marginBottom": "16px"}),
                dcc.Graph(figure=price_graph, config={"displayModeBar": False}),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginBottom": "24px"}),

        # Row 4: Conflict Highlights (2 panels)
        html.Div([
            html.Div([
                html.H2("Daily Top 5 Conflict Highlights", style={"marginBottom": "16px"}),
                dash_table.DataTable(
                    columns=[
                        {"name": "Date", "id": "Date"},
                        {"name": "Highlight", "id": "Highlight"},
                        {"name": "Region", "id": "Region"},
                        {"name": "Source", "id": "Source"},
                        {"name": "Link", "id": "Link", "presentation": "markdown"},
                    ],
                    data=conflict_global.assign(Link=conflict_global.apply(lambda row: f"[{row['Source']}]({row['Link']})", axis=1)).to_dict("records"),
                    page_size=5,
                    style_cell={"textAlign": "left", "padding": "8px", "whiteSpace": "normal", "height": "auto"},
                    style_header={"backgroundColor": "#123a5e", "fontWeight": "bold", "color": "white"},
                    style_data={"backgroundColor": "#f8fbff", "color": "#111"},
                    style_table={"overflowX": "auto"},
                ),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
            html.Div([
                html.H2("Indian Highlights", style={"marginBottom": "16px"}),
                dash_table.DataTable(
                    columns=[
                        {"name": "Date", "id": "Date"},
                        {"name": "Highlight", "id": "Highlight"},
                        {"name": "Region", "id": "Region"},
                        {"name": "Source", "id": "Source"},
                        {"name": "Link", "id": "Link", "presentation": "markdown"},
                    ],
                    data=conflict_india.assign(Link=conflict_india.apply(lambda row: f"[{row['Source']}]({row['Link']})", axis=1)).to_dict("records"),
                    page_size=5,
                    style_cell={"textAlign": "left", "padding": "8px", "whiteSpace": "normal", "height": "auto"},
                    style_header={"backgroundColor": "#123a5e", "fontWeight": "bold", "color": "white"},
                    style_data={"backgroundColor": "#f8fbff", "color": "#111"},
                    style_table={"overflowX": "auto"},
                ),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginBottom": "24px"}),

        # Row 5: Economy and Stock Markets (2 panels)
        html.Div([
            html.Div([
                html.H2("Global Economy Highlights", style={"marginBottom": "16px"}),
                html.Ul([
                    html.Li([
                        html.A(item["Headline"], href=item["Link"], target="_blank", style={"color": "#0057d9", "textDecoration": "none"}),
                        html.Span(f" — {item['Source']}", style={"color": "#555", "marginLeft": "8px"}),
                    ])
                    for item in global_economy_highlights
                ], style={"paddingLeft": "18px", "color": "#222"}),
                html.H2("Monthly Geopolitical Scenario", style={"marginTop": "28px", "marginBottom": "16px"}),
                dash_table.DataTable(
                    columns=[
                        {"name": "Month", "id": "Month"},
                        {"name": "Standing", "id": "Standing"},
                        {"name": "Concern", "id": "Concern"},
                        {"name": "Source", "id": "Source"},
                        {"name": "Link", "id": "Link", "presentation": "markdown"},
                    ],
                    data=geo_monthly_standings.assign(Link=geo_monthly_standings.apply(lambda row: f"[{row['Source']}]({row['Link']})", axis=1)).to_dict("records"),
                    style_cell={"textAlign": "left", "padding": "8px", "whiteSpace": "normal", "height": "auto"},
                    style_header={"backgroundColor": "#0b2d4f", "fontWeight": "bold", "color": "white"},
                    style_data={"backgroundColor": "#f4f7fb", "color": "#111"},
                    style_table={"overflowX": "auto"},
                    page_size=4,
                ),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
            html.Div([
                html.H2("Global & National Stock Markets", style={"marginBottom": "16px"}),
                dcc.Graph(figure=stock_market_fig, config={"displayModeBar": False}),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginBottom": "24px"}),

        # Row 6: District News and Security (2 panels)
        html.Div([
            html.Div([
                html.H2("India District News Highlights", style={"marginBottom": "16px"}),
                dash_table.DataTable(
                    columns=[
                        {"name": "District", "id": "District"},
                        {"name": "Headline", "id": "Headline"},
                        {"name": "Source", "id": "Source"},
                        {"name": "Link", "id": "Link", "presentation": "markdown"},
                    ],
                    data=district_news.assign(Link=district_news.apply(lambda row: f"[{row['Source']}]({row['Link']})", axis=1)).to_dict("records"),
                    page_size=5,
                    style_cell={"textAlign": "left", "padding": "8px", "whiteSpace": "normal", "height": "auto"},
                    style_header={"backgroundColor": "#0b2d4f", "fontWeight": "bold", "color": "white"},
                    style_data={"backgroundColor": "#fefefe", "color": "#111"},
                    style_table={"overflowX": "auto"},
                ),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
            html.Div([
                html.H2("Security & National Highlights", style={"marginBottom": "16px"}),
                html.Ul([
                    html.Li([
                        html.A(item["Headline"], href=item["Link"], target="_blank", style={"color": "#0057d9", "textDecoration": "none"}),
                        html.Span(f" — {item['Source']}", style={"color": "#555", "marginLeft": "8px"}),
                    ])
                    for item in security_highlights
                ], style={"paddingLeft": "18px", "color": "#222"}),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginBottom": "24px"}),

        # Row 7: Geospatial Intelligence (2 panels)
        html.Div([
            html.Div([
                html.H2("Geospatial Intelligence — Uploaded JSON", style={"marginBottom": "16px"}),
                html.Div(id="geojson-preview", style={"padding": "18px", "backgroundColor": "#f4f7fb", "borderRadius": "16px", "minHeight": "260px", "color": "#111"}, children=[
                    html.P("Upload a JSON file to preview the geospatial intelligence data here."),
                ]),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
            html.Div([
                html.H2("Geospatial Intelligence — Uploaded PDF", style={"marginBottom": "16px"}),
                html.Div(id="pdf-preview", style={"padding": "18px", "backgroundColor": "#f4f7fb", "borderRadius": "16px", "minHeight": "260px", "color": "#111"}, children=[
                    html.P("Upload a PDF to display the intelligence report preview here."),
                ]),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginBottom": "24px"}),

        # Row 8: YouTube and AI Intelligence (2 panels)
        html.Div([
            html.Div([
                html.H2("Live YouTube Footage Channels", style={"marginBottom": "12px"}),
                html.P("All embedded YouTube feeds are live stream sources and will play using the supplied live video links.", style={"marginTop": "0", "color": "#444"}),
                html.Div([
                    html.Div([
                        html.H4(feed["title"]),
                        html.Iframe(
                            src=feed["embed"],
                            style={"width": "100%", "height": "270px", "border": "0", "borderRadius": "10px"},
                            title=feed["title"],
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen",
                        ),
                        html.P(f"Source: {feed['source']}", style={"marginTop": "8px", "color": "#666"}),
                    ], style={"marginBottom": "24px"})
                    for feed in youtube_live_streams
                ])
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
            html.Div([
                html.H2("Gemini AI Intelligence — Quick Brief", style={"marginBottom": "16px"}),
                html.Div([
                    html.P("Gemini says:", style={"margin": "0 0 12px 0", "fontWeight": "700"}),
                    html.P(
                        "Monitor thermal anomalies near the LAC, validate elevated satellite change detection with public CCTV feeds, and cross-reference local OSINT chatter for early escalation signals.",
                    ),
                    html.Ul([
                        html.Li("Priority 1: Northern LAC glacier passes and trans-Himalayan logistics corridors."),
                        html.Li("Priority 2: YouTube / public webcams for rapid visual confirmation."),
                        html.Li("Priority 3: ACLED + GDELT for cross-border incident correlation."),
                    ]),
                    html.Div([
                        html.H4("Key regional focus areas"),
                        html.P("Ladakh, Arunachal Pradesh, Sikkim and the Kashmir Line of Control."),
                    ], style={"marginTop": "20px", "padding": "16px", "borderRadius": "12px", "backgroundColor": "#f3f7fb"}),
                ], style={"padding": "20px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.08)"}),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginBottom": "24px"}),

        # Row 9: Terrorism (2 panels)
        html.Div([
            html.Div([
                html.H2("Terrorism Incident Points", style={"marginBottom": "16px"}),
                html.P(["Terrorism Data Portal: ", html.A("Decision Support System and Better data Visualisation", href="https://rgatport.streamlit.app/", target="_blank", style={"color": "#0057d9", "textDecoration": "underline"})], style={"marginTop": "0", "color": "#444", "marginBottom": "12px"}),
                dcc.Graph(id="terrorism-activity-map", figure=terrorism_map_fig, config={"displayModeBar": False}),
                html.Div(id="terrorism-incident-details", style={"marginTop": "16px", "padding": "18px", "backgroundColor": "#f7fbff", "borderRadius": "16px", "boxShadow": "0 10px 24px rgba(0,0,0,0.05)", "minHeight": "150px", "color": "#222"}),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
            html.Div([
                html.H2("Terrorism Network Model", style={"marginBottom": "16px"}),
                dcc.Graph(figure=terrorism_network_fig, config={"displayModeBar": False}),
                html.H4("State-wise Active Perpetrator Groups", style={"marginTop": "20px", "marginBottom": "12px"}),
                dash_table.DataTable(
                    columns=[
                        {"name": "State", "id": "State"},
                        {"name": "Active Group", "id": "Active Group"},
                        {"name": "Events", "id": "Events"},
                    ],
                    data=state_group_summary.to_dict("records"),
                    page_size=10,
                    style_cell={"textAlign": "left", "padding": "8px", "whiteSpace": "normal", "height": "auto"},
                    style_header={"backgroundColor": "#0b2d4f", "fontWeight": "bold", "color": "white"},
                    style_data={"backgroundColor": "#fdfdfd", "color": "#111"},
                    style_table={"overflowX": "auto"},
                ),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginBottom": "24px"}),

        # Row 10: Terrorism Details (1 panel, full width)
        html.Div([
            html.Div([
                html.H2("Terrorism Incident Details", style={"marginBottom": "16px"}),
                dash_table.DataTable(
                    columns=terrorism_details_columns,
                    data=terrorism_events.to_dict("records"),
                    page_size=10,
                    style_cell={"textAlign": "left", "padding": "8px", "whiteSpace": "normal", "height": "auto"},
                    style_header={"backgroundColor": "#0b2447", "fontWeight": "bold", "color": "white"},
                    style_data={"backgroundColor": "#f9f9fb", "color": "#111"},
                    style_table={"overflowX": "auto"},
                ),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
        ], style={"display": "grid", "gridTemplateColumns": "1fr", "gap": "16px", "marginBottom": "24px"}),

        # Row 11: OSINT and Conflict (2 panels)
        html.Div([
            html.Div([
                html.H2("OSINT Alert Trend", style={"marginBottom": "16px"}),
                dcc.Graph(
                    figure=px.area(
                        osint_trend,
                        x="date",
                        y="event_count",
                        title="GDELT + Telegram Event Signals",
                        labels={"date": "Date", "event_count": "Event Count"},
                    ).update_layout(margin={"t": 40, "l": 0, "r": 0, "b": 0}),
                    config={"displayModeBar": False},
                ),
                html.P(
                    "This trend line tracks daily open-source intelligence volumes from GDELT news event feeds and Telegram chatter. Spikes often flag emerging conflict incidents, protest mobilization, or heightened messaging operations.",
                    style={"margin": "16px 0 0 0", "color": "#333"},
                ),
                html.Ul([
                    html.Li("Higher values indicate accelerated reporting and operational intensity."),
                    html.Li("Sustained elevated signal volume may point to a broader escalation or multi-domain campaign."),
                    html.Li("Use this curve to detect early warning surges and correlate them with tactical cluster activity."),
                ], style={"paddingLeft": "18px", "color": "#333"}),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
            html.Div([
                html.H2("Conflict Event Mix", style={"marginBottom": "16px"}),
                dcc.Graph(
                    figure=px.bar(
                        conflict_summary,
                        x="event_type",
                        y="count",
                        color="event_type",
                        title="ACLED-style Conflict Categories",
                        labels={"event_type": "Event Type", "count": "Count"},
                    ).update_layout(showlegend=False, margin={"t": 40, "l": 0, "r": 0, "b": 0}),
                    config={"displayModeBar": False},
                ),
                html.P(
                    "This category mix distinguishes between the nature of incidents observed: direct engagements, patrols, surveillance operations, logistics activity, and diplomatic actions.",
                    style={"margin": "16px 0 0 0", "color": "#333"},
                ),
                html.Ul([
                    html.Li(f"Skirmish: {conflict_event_definitions['Skirmish']}"),
                    html.Li(f"Patrol: {conflict_event_definitions['Patrol']}"),
                    html.Li(f"Observation: {conflict_event_definitions['Observation']}"),
                    html.Li(f"Infrastructure: {conflict_event_definitions['Infrastructure']}"),
                    html.Li(f"Diplomatic: {conflict_event_definitions['Diplomatic']}"),
                ], style={"paddingLeft": "18px", "color": "#333"}),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginBottom": "24px"}),

        # Row 12: Thermal and Climate (2 panels)
        html.Div([
            html.Div([
                html.H2("Thermal Hotspots & Fires", style={"marginBottom": "16px"}),
                dcc.Graph(figure=fire_fig, config={"displayModeBar": False}),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
            html.Div([
                html.H2("Power / Climate Signals", style={"marginBottom": "16px"}),
                dcc.Graph(
                    figure=px.line(
                        power_climate,
                        x="date",
                        y=["solar_index", "precipitation"],
                        title="Renewable Signal & Precipitation",
                        labels={"value": "Index / mm", "variable": "Signal"},
                    ).update_layout(margin={"t": 40, "l": 0, "r": 0, "b": 0}),
                    config={"displayModeBar": False},
                ),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
        ], style={"display": "grid", "gridTemplateColumns": "1fr 1fr", "gap": "16px", "marginBottom": "24px"}),

        # Row 13: Weather (1 panel, full width)
        html.Div([
            html.Div([
                html.H2("Live Weather Watchpoints", style={"marginBottom": "16px"}),
                dcc.Graph(id="weather-point-map", figure=weather_map_fig, config={"displayModeBar": False}),
                html.P(
                    "Select any point on the weather watch map to reveal live local weather conditions for that sector.",
                    style={"margin": "16px 0 0 0", "color": "#333"},
                ),
                html.Div(id="weather-point-details", style={"marginTop": "16px", "padding": "18px", "backgroundColor": "#f6fbff", "borderRadius": "16px", "boxShadow": "0 10px 24px rgba(0,0,0,0.05)", "color": "#222"}),
            ], style={"padding": "18px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}),
        ], style={"display": "grid", "gridTemplateColumns": "1fr", "gap": "16px", "marginBottom": "24px"}),

        # Row 14: Custom Panels (dynamic grid)
        html.Div(id="custom-panels", style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(300px, 1fr))", "gap": "16px", "marginBottom": "24px"}),
    ], style={"padding": "0 24px"}),

    html.Div([
        html.P(["For Global Data Monitoring Visit : ", html.A("https://www.worldmonitor.app/", href="https://www.worldmonitor.app/", target="_blank", style={"color": "#0057d9", "textDecoration": "underline"})], style={"textAlign": "center", "padding": "18px", "margin": "0", "color": "#333", "backgroundColor": "#e9f2fc", "borderRadius": "12px", "margin": "0 24px 24px 24px"}),
    ]),
], style={"backgroundColor": "#eff3f8", "color": "#111", "fontFamily": "Inter, Arial, sans-serif"})





@app.callback(
    Output("custom-panels-store", "data"),
    Output("custom-panel-response", "children"),
    Input("add-panel-button", "n_clicks"),
    State("custom-panel-title", "value"),
    State("custom-panel-content", "value"),
    State("custom-panels-store", "data"),
    prevent_initial_call=True,
)
def add_custom_panel(n_clicks, title, content, panels_data):
    if not title or not content:
        return panels_data, html.P("Please provide both title and content for the new panel.", style={"color": "#ffb3b3"})

    panels = panels_data or []
    panels.append({
        "type": "custom",
        "title": title,
        "content": content,
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    })
    return panels, html.P("Panel added successfully and will appear below.", style={"color": "#cfe8ff"})


@app.callback(
    Output("custom-panels", "children"),
    Input("custom-panels-store", "data"),
)
def render_custom_panels(panels_data):
    if not panels_data:
        return html.Div("No custom panels created yet.", style={"textAlign": "center", "padding": "40px", "color": "#666", "fontStyle": "italic"})

    children = []
    for panel in panels_data:
        if panel.get("type") == "json":
            children.append(html.Div([
                html.H3(panel.get("title", "Untitled JSON"), style={"margin": "0 0 12px 0", "color": "#2a9d8f"}),
                html.Div(panel.get("preview", "No preview available"), style={"backgroundColor": "#f8f9fa", "padding": "12px", "borderRadius": "8px", "fontFamily": "monospace", "fontSize": "12px", "color": "#333"}),
                html.Small(f"Uploaded: {panel.get('time', '')}", style={"color": "#888", "marginTop": "8px", "display": "block"}),
            ], style={"padding": "20px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}))
        elif panel.get("type") == "pdf":
            children.append(html.Div([
                html.H3(panel.get("title", "Untitled PDF"), style={"margin": "0 0 12px 0", "color": "#e76f51"}),
                html.Iframe(src=panel.get("embed_url", ""), style={"width": "100%", "height": "400px", "border": "1px solid #ddd", "borderRadius": "8px"}),
                html.Small(f"Uploaded: {panel.get('time', '')}", style={"color": "#888", "marginTop": "8px", "display": "block"}),
            ], style={"padding": "20px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}))
        else:
            children.append(html.Div([
                html.H3(panel.get("title", "Untitled"), style={"margin": "0 0 12px 0", "color": "#264653"}),
                html.P(panel.get("content", ""), style={"margin": "0 0 12px 0", "lineHeight": "1.6", "color": "#333"}),
                html.Small(f"Created: {panel.get('time', '')}", style={"color": "#888"}),
            ], style={"padding": "20px", "backgroundColor": "white", "borderRadius": "16px", "boxShadow": "0 12px 30px rgba(0,0,0,0.06)"}))

    return children


@app.callback(
    Output("geojson-preview", "children"),
    Output("upload-response", "children"),
    Output("custom-panels-store", "data"),
    Input("submit-json", "n_clicks"),
    State("upload-json", "contents"),
    State("upload-json", "filename"),
    State("json-title", "value"),
    State("custom-panels-store", "data"),
    prevent_initial_call=True,
)
def handle_json_upload(n_clicks, contents, filename, title, panels_data):
    if not contents:
        return dash.no_update, html.P("Please select a JSON file before submitting.", style={"color": "#ffb3b3"}), panels_data

    title_display = title or filename or "Uploaded JSON"
    preview = parse_json_preview(contents, filename, title_display)
    new_panel = {
        "type": "json",
        "title": title_display,
        "content": "JSON uploaded. Use preview section for details.",
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    panels = panels_data or []
    panels.append(new_panel)

    return preview, html.P("JSON upload received and visualised.", style={"color": "#cfe8ff"}), panels


@app.callback(
    Output("pdf-preview", "children"),
    Output("upload-response", "children"),
    Output("custom-panels-store", "data"),
    Input("submit-pdf", "n_clicks"),
    State("upload-pdf", "contents"),
    State("upload-pdf", "filename"),
    State("pdf-title", "value"),
    State("custom-panels-store", "data"),
    prevent_initial_call=True,
)
def handle_pdf_upload(n_clicks, contents, filename, title, panels_data):
    if not contents:
        return dash.no_update, html.P("Please select a PDF file before submitting.", style={"color": "#ffb3b3"}), panels_data

    title_display = title or filename or "Uploaded PDF"
    preview = render_pdf_preview(contents, filename, title_display)
    new_panel = {
        "type": "pdf",
        "title": title_display,
        "content": "PDF uploaded and preview shown.",
        "time": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    panels = panels_data or []
    panels.append(new_panel)

    return preview, html.P("PDF upload received and visualised.", style={"color": "#cfe8ff"}), panels


def parse_json_preview(contents, filename, title):
    if not contents:
        return html.P("No JSON file provided.")
    content_type, content_string = contents.split(",", 1)
    decoded = base64.b64decode(content_string)
    try:
        data = json.loads(decoded.decode("utf-8"))
        preview_text = json.dumps(data, indent=2)
    except Exception as e:
        return html.Div([html.P(f"Unable to parse JSON: {e}")])
    return html.Div([
        html.H4(title or filename, style={"marginTop": "0", "marginBottom": "12px"}),
        html.Pre(preview_text[:1600], style={"whiteSpace": "pre-wrap", "wordBreak": "break-word", "maxHeight": "380px", "overflowY": "auto", "backgroundColor": "#eef4fb", "padding": "12px", "borderRadius": "10px"}),
    ])


def render_pdf_preview(contents, filename, title):
    if not contents:
        return html.P("No PDF file provided.")
    return html.Div([
        html.H4(title or filename, style={"marginTop": "0", "marginBottom": "12px"}),
        html.Iframe(src=contents, style={"width": "100%", "height": "420px", "border": "1px solid #dce4f2", "borderRadius": "12px"}),
    ])




@app.callback(
    Output("weather-point-details", "children"),
    Input("weather-point-map", "clickData"),
)
def update_weather_point_details(clickData):
    selected_site = weather_points["site"].iloc[0]
    if clickData and clickData.get("points"):
        if clickData["points"][0].get("customdata"):
            selected_site = clickData["points"][0]["customdata"][0]
    info = weather_point_info.get(selected_site)
    if not info:
        return html.Div("Select a point on the weather map to view live local weather details.")
    return html.Div([
        html.H4(f"{selected_site} — Live Weather", style={"marginTop": "0", "marginBottom": "12px"}),
        html.P(f"Condition: {info['condition']}", style={"margin": "0 0 8px 0"}),
        html.P(f"Temperature: {info['temperature']}°C", style={"margin": "0 0 8px 0"}),
        html.P(f"Humidity: {info['humidity']}%", style={"margin": "0 0 8px 0"}),
        html.P(f"Wind Speed: {info['wind_kmh']} km/h", style={"margin": "0 0 8px 0"}),
        html.P(f"Forecast: {info['forecast']}", style={"margin": "0 0 8px 0"}),
        html.P(f"Alert: {info['alert']}", style={"margin": "0"}),
    ], style={"lineHeight": "1.8"})

@app.callback(
    Output("terrorism-incident-details", "children"),
    Input("terrorism-activity-map", "clickData"),
)
def update_terrorism_incident_details(clickData):
    if not clickData or not clickData.get("points"):
        return html.Div("Click any terrorism incident point on the map to view full event details.", style={"color": "#333"})
    custom = clickData["points"][0].get("customdata")
    if not custom or len(custom) < 8:
        return html.Div("Incident data unavailable.", style={"color": "#333"})
    event, location, state, group, status, deaths, injuries, description = custom
    return html.Div([
        html.H4(event, style={"marginTop": "0", "marginBottom": "12px"}),
        html.P(f"Location: {location}, {state}", style={"margin": "0 0 8px 0"}),
        html.P(f"Group: {group}", style={"margin": "0 0 8px 0"}),
        html.P(f"Status: {status}", style={"margin": "0 0 8px 0"}),
        html.P(f"Casualties: {deaths} deaths, {injuries} injuries", style={"margin": "0 0 8px 0"}),
        html.P(f"Description: {description}", style={"margin": "0"}),
    ], style={"lineHeight": "1.8"})


@app.callback(
    Output("live-news-list", "children"),
    Output("ai-summary", "children"),
    Output("last-updated-text", "children"),
    Output("last-updated-banner", "children"),
    Input("refresh-interval", "n_intervals"),
)
def refresh_live_dashboard(n_intervals):
    update_context = refresh_dashboard_data()
    news_children = []
    for item in update_context["news_items"]:
        news_children.append(
            html.Li(
                html.A(item["title"], href=item["url"], target="_blank", style={"color": "#0057d9", "textDecoration": "none"}),
                style={"marginBottom": "8px"},
            )
        )
    summary_text = generate_ai_summary(update_context)
    last_stamp = current_timestamp()
    last_text = f"Last refresh: {last_stamp}"
    banner_text = f"Dashboard auto-refresh triggered at {last_stamp}."
    return news_children, summary_text, last_text, banner_text


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8050, debug=False)

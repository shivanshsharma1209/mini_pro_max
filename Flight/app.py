from flask import Flask, request, render_template
from config import Config
from flight_serpapi import get_flights_serpapi

import csv, math, time
from datetime import datetime
from geopy.geocoders import Nominatim

app = Flask(__name__)
app.config.from_object(Config)

# ==================================================
# GEO SETUP
# ==================================================
geolocator = Nominatim(user_agent="multimodal_travel")
geo_cache  = {}

def get_lat_lon(place):
    if place in geo_cache:
        return geo_cache[place]
    try:
        loc = geolocator.geocode(place + ", India", timeout=10)
        time.sleep(1)
        if loc:
            geo_cache[place] = (loc.latitude, loc.longitude)
            return geo_cache[place]
    except:
        pass
    return None, None

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))

# ==================================================
# LOAD AIRPORTS
# ==================================================
def load_airports(csv_file):
    airports = []
    with open(csv_file, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                if r["iso_country"] == "IN" and r["iata_code"].strip():
                    airports.append({
                        "code": r["iata_code"].strip(),
                        "name": r["name"].strip(),
                        "lat":  float(r["latitude_deg"]),
                        "lon":  float(r["longitude_deg"])
                    })
            except:
                continue
    return airports

airports = load_airports("airports.csv")

def find_nearest_airport(lat, lon):
    return min(airports, key=lambda a: haversine(lat, lon, a["lat"], a["lon"]))

# ==================================================
# ROUTES
# ==================================================
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/results")
def results():

    # ── Get user input ────────────────────────────────────────
    from_place = request.args.get("from_place", "").strip()
    to_place   = request.args.get("to_place",   "").strip()
    date       = request.args.get("date",        "").strip()  # YYYY-MM-DD

    if not from_place or not to_place or not date:
        return render_template("error.html", message="Please fill all fields."), 400

    # ── Geocode locations ─────────────────────────────────────
    from_lat, from_lon = get_lat_lon(from_place)
    to_lat,   to_lon   = get_lat_lon(to_place)

    if not from_lat or not to_lat:
        return render_template("error.html", message="Could not find one or both locations."), 400

    # ── Find nearest airports ─────────────────────────────────
    from_airport = find_nearest_airport(from_lat, from_lon)
    to_airport   = find_nearest_airport(to_lat,   to_lon)

    # ── Fetch flights via SerpAPI ─────────────────────────────
    raw_flights = get_flights_serpapi(
        from_airport["code"],
        to_airport["code"],
        date
    )

    # ── Build display list ────────────────────────────────────
    flights_list = []
    for idx, f in enumerate(raw_flights, start=1):

        # Fix ₹0 prices (Air India Express sometimes hides price in free tier)
        price_display = f"₹ {f['price_inr']:,}" if f["price_inr"] > 0 else "Check site"

        flights_list.append({
            "rank":       idx,
            "airline":    f["airline"],
            "flight_no":  f["flight_no"],
            "airplane":   f.get("airplane", ""),
            "route":      f["route"],
            "departure":  f["departure"],
            "arrival":    f["arrival"],
            "duration":   f["duration"],
            "stops":      "Non-stop" if f["stops"] == 0 else f"{f['stops']} stop(s)",
            "price":      price_display,
            "price_raw":  f["price_inr"],
            "carbon_kg":  f.get("carbon_kg", 0),
        })

    return render_template(
        "results.html",
        flights=flights_list,
        from_place=from_place,
        to_place=to_place,
        from_airport=from_airport,
        to_airport=to_airport,
        date=date,
        total=len(flights_list)
    )


# ==================================================
# RUN
# ==================================================
if __name__ == "__main__":
    app.run(debug=True)
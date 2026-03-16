"""
flight_serpapi.py
-----------------
Place this file inside: Multi Modal System/Flight/flight_serpapi.py

Fetches real Indian domestic flight data from Google Flights via SerpAPI.
- Real airline names, flight numbers, departure/arrival times, prices in INR
- Smart caching: same route+date reuses result for 6 hours (saves free quota)
- 100 free searches/month at serpapi.com (no credit card needed)

Install: pip install requests
"""

import requests
import json
import os
from datetime import datetime, timedelta

# ==================================================
# ✅ STEP 1: Paste your SerpAPI key here
#    Get it free at: https://serpapi.com → Sign Up → Dashboard
# ==================================================
SERPAPI_KEY = "ef252767c19fe7815e9077876bb9872bc260a1ae1d63a6f243adc51f16761382"

SERPAPI_URL = "https://serpapi.com/search"
CACHE_FILE  = "flight_cache.json"     # Created automatically in your project folder
CACHE_TTL_HOURS = 6                   # Reuse cached results for 6 hours


# ==================================================
# CACHE SYSTEM
# Prevents burning API calls for same route+date
# ==================================================

def _load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def _save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

def _cache_key(origin, dest, date):
    return f"{origin}_{dest}_{date}"

def _get_cached(origin, dest, date):
    cache = _load_cache()
    key   = _cache_key(origin, dest, date)
    if key in cache:
        saved_at = datetime.fromisoformat(cache[key]["saved_at"])
        if datetime.now() - saved_at < timedelta(hours=CACHE_TTL_HOURS):
            print(f"  [Cache HIT] {origin}→{dest} on {date} — no API call used")
            return cache[key]["flights"]
    return None

def _write_cache(origin, dest, date, flights):
    cache = _load_cache()
    cache[_cache_key(origin, dest, date)] = {
        "saved_at": datetime.now().isoformat(),
        "flights":  flights
    }
    _save_cache(cache)


# ==================================================
# PARSE SERPAPI RESPONSE
# Converts raw JSON → clean list of flight dicts
# ==================================================

def _parse(raw, origin_iata, dest_iata):
    flights = []

    # SerpAPI splits results into best_flights and other_flights
    all_offers = raw.get("best_flights", []) + raw.get("other_flights", [])

    if not all_offers:
        return []

    for offer in all_offers:
        legs = offer.get("flights", [])
        if not legs:
            continue

        first = legs[0]
        last  = legs[-1]

        # Route string: DEL → BOM  or  DEL → HYD → BOM
        route_parts = [l["departure_airport"]["id"] for l in legs]
        route_parts.append(last["arrival_airport"]["id"])
        route = " → ".join(route_parts)

        # Duration
        total_min = offer.get("total_duration", 0)
        duration  = f"{total_min // 60}h {total_min % 60}m"

        # Price (INR because we pass currency=INR)
        price_inr = int(offer.get("price", 0))

        # Carbon emissions
        carbon_g  = offer.get("carbon_emissions", {}).get("this_flight", 0)
        carbon_kg = round(carbon_g / 1000, 1) if carbon_g else 0

        # Layover info
        layovers     = offer.get("layovers", [])
        layover_info = ", ".join(
            f"{l.get('name','?')} ({l.get('duration',0)//60}h {l.get('duration',0)%60}m)"
            for l in layovers
        ) if layovers else ""

        flights.append({
            # Core display fields
            "source":       "Google Flights",
            "airline":      first.get("airline", "Unknown"),
            "flight_no":    first.get("flight_number", ""),
            "airplane":     first.get("airplane", ""),
            "route":        route,
            "departure":    first["departure_airport"].get("time", ""),
            "arrival":      last["arrival_airport"].get("time", ""),
            "duration":     duration,
            "stops":        len(legs) - 1,
            "price_inr":    price_inr,
            # Extra fields for recommender module
            "carbon_kg":    carbon_kg,
            "layovers":     layover_info,
            "travel_class": first.get("travel_class", "Economy"),
            "extensions":   first.get("extensions", []),
        })

    return sorted(flights, key=lambda x: x["price_inr"])


# ==================================================
# MAIN FUNCTION — import and use this in app.py
# ==================================================

def get_flights_serpapi(origin_iata, dest_iata, date_str):
    """
    Returns real Indian domestic flight data from Google Flights.

    Args:
        origin_iata  : IATA code  e.g. "DEL"
        dest_iata    : IATA code  e.g. "BOM"
        date_str     : YYYY-MM-DD e.g. "2025-08-15"

    Returns:
        List of flight dicts sorted by price (cheapest first).
        Each dict has: airline, flight_no, route, departure, arrival,
                       duration, stops, price_inr, carbon_kg

    Usage in app.py:
        from flight_serpapi import get_flights_serpapi
        flights = get_flights_serpapi(
            from_airport["code"],
            to_airport["code"],
            date   # YYYY-MM-DD
        )
    """

    print(f"\n  Searching flights: {origin_iata} → {dest_iata} on {date_str}")

    # Step 1: Check cache
    cached = _get_cached(origin_iata, dest_iata, date_str)
    if cached is not None:
        return cached

    # Step 2: Validate key
    if SERPAPI_KEY == "YOUR_SERPAPI_KEY_HERE":
        print("  ERROR: SerpAPI key not set!")
        print("  Get free key at https://serpapi.com then paste in flight_serpapi.py")
        return []

    # Step 3: Call API
    params = {
        "engine":        "google_flights",
        "departure_id":  origin_iata,
        "arrival_id":    dest_iata,
        "outbound_date": date_str,
        "type":          "2",        # one-way
        "hl":            "en",
        "currency":      "INR",
        "gl":            "in",
        "api_key":       SERPAPI_KEY
    }

    try:
        resp = requests.get(SERPAPI_URL, params=params, timeout=15)

        if resp.status_code == 401:
            print("  ERROR: Invalid SerpAPI key")
            return []
        if resp.status_code == 429:
            print("  ERROR: SerpAPI 100 search/month limit reached")
            return []
        if resp.status_code != 200:
            print(f"  ERROR: SerpAPI returned status {resp.status_code}")
            return []

        raw = resp.json()

    except requests.exceptions.Timeout:
        print("  ERROR: SerpAPI request timed out")
        return []
    except Exception as e:
        print(f"  ERROR: {e}")
        return []

    # Step 4: Handle API-level errors
    if "error" in raw:
        print(f"  SerpAPI error: {raw['error']}")
        return []

    if "best_flights" not in raw and "other_flights" not in raw:
        print(f"  No flights found: {origin_iata}→{dest_iata} on {date_str}")
        return []

    # Step 5: Parse, cache, return
    flights = _parse(raw, origin_iata, dest_iata)
    _write_cache(origin_iata, dest_iata, date_str, flights)
    print(f"  Found {len(flights)} flights — cached for {CACHE_TTL_HOURS}h")
    return flights


# ==================================================
# CHECK QUOTA
# ==================================================

def check_quota():
    """Prints your remaining SerpAPI free searches for the month."""
    if SERPAPI_KEY == "YOUR_SERPAPI_KEY_HERE":
        print("Add your SerpAPI key first.")
        return None
    resp  = requests.get("https://serpapi.com/account", params={"api_key": SERPAPI_KEY})
    data  = resp.json()
    left  = data.get("plan_searches_left", "?")
    total = data.get("plan_monthly_searches", "?")
    print(f"SerpAPI quota: {left} / {total} searches remaining this month")
    return left


# ==================================================
# HOW TO USE IN app.py  (copy-paste guide)
# ==================================================
#
# ── 1. Add import at top of app.py ───────────────
#    from flight_serpapi import get_flights_serpapi
#
# ── 2. Replace search_amadeus_flights() call ─────
#    raw_flights = get_flights_serpapi(
#        from_airport["code"],    # e.g. "DEL"
#        to_airport["code"],      # e.g. "BOM"
#        date                     # YYYY-MM-DD from form
#    )
#
# ── 3. Build display list ────────────────────────
#    flights_list = []
#    for idx, f in enumerate(raw_flights, start=1):
#        flights_list.append([
#            idx,
#            f["airline"],
#            f["flight_no"],
#            f["route"],
#            f["departure"],
#            f["arrival"],
#            f["duration"],
#            f["stops"],
#            f"₹ {f['price_inr']}"
#        ])
#
#    columns = ["#", "Airline", "Flight No", "Route",
#               "Departure", "Arrival", "Duration", "Stops", "Price"]
#
# ==================================================


# ==================================================
# TEST — run: python flight_serpapi.py
# ==================================================
if __name__ == "__main__":
    print("=" * 55)
    print("  Flight SerpAPI — Test")
    print("=" * 55)

    if SERPAPI_KEY == "YOUR_SERPAPI_KEY_HERE":
        print("\nYou haven't added your SerpAPI key yet!")
        print("  1. Go to https://serpapi.com and sign up (free, no card)")
        print("  2. Copy your API key from the dashboard")
        print("  3. Paste it at the top of flight_serpapi.py")
    else:
        check_quota()
        results = get_flights_serpapi("DEL", "BOM", "2026-04-15")

        if results:
            print(f"\n{'─' * 95}")
            print(f"{'#':<3} {'Airline':<22} {'Flight':<9} {'Departure':<18} "
                  f"{'Arrival':<18} {'Duration':<9} {'Stops':<6} {'Price':<10} {'CO2'}")
            print(f"{'─' * 95}")
            for i, f in enumerate(results, 1):
                print(
                    f"{i:<3} {f['airline']:<22} {f['flight_no']:<9} "
                    f"{f['departure']:<18} {f['arrival']:<18} "
                    f"{f['duration']:<9} {f['stops']:<6} "
                    f"₹{f['price_inr']:<9} {f['carbon_kg']}kg"
                )
        else:
            print("\nNo results. Check your key or try a different route/date.")
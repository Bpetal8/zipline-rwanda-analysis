"""
generate_data.py
----------------
Generates synthetic but realistic Zipline flight datasets modelled on the
publicly available Muhanga distribution centre data (Rwanda).

Two output files:
  data/flights_summary.csv   — one row per flight (launch time, weather, battery, outcome)
  data/flight_telemetry.csv  — position/velocity samples per flight (time-series)

Run:  python data/generate_data.py
"""

import csv
import random
import math
from datetime import datetime, timedelta

random.seed(42)

# ── Constants ──────────────────────────────────────────────────────────────────
MUHANGA_LAT  =  -2.0833
MUHANGA_LON  =  29.6167

# Hospitals within ~50 km of Muhanga that Zipline serves
HOSPITALS = [
    {"name": "Kabgayi District Hospital",   "lat": -2.0200, "lon": 29.7500, "district": "Muhanga"},
    {"name": "Ruhango District Hospital",   "lat": -2.2167, "lon": 29.7833, "district": "Ruhango"},
    {"name": "Kabutare District Hospital",  "lat": -2.5833, "lon": 29.7333, "district": "Huye"},
    {"name": "Kibogora Hospital",           "lat": -2.3333, "lon": 29.0667, "district": "Nyamasheke"},
    {"name": "Byumba District Hospital",    "lat": -1.5833, "lon": 30.0667, "district": "Gicumbi"},
    {"name": "Rwamagana District Hospital", "lat": -1.9500, "lon": 30.4333, "district": "Rwamagana"},
]

BLOOD_PRODUCTS  = ["Whole Blood", "Packed Red Cells", "Fresh Frozen Plasma", "Platelets"]
WEATHER_CONDITIONS = ["Clear", "Partly Cloudy", "Overcast", "Light Rain", "Foggy"]
FLIGHT_OUTCOMES    = ["Delivered", "Delivered", "Delivered", "Delivered", "Returned - Weather",
                       "Returned - Technical", "Partial Delivery"]

# ── Helpers ────────────────────────────────────────────────────────────────────
def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))

def random_timestamp(start, end):
    delta = end - start
    return start + timedelta(seconds=random.randint(0, int(delta.total_seconds())))

# ── Generate flights_summary.csv ───────────────────────────────────────────────
start_date = datetime(2023, 1, 1, 6, 0)
end_date   = datetime(2023, 12, 31, 20, 0)

flights = []
for flight_id in range(1, 1201):   # ~1200 flights across the year
    hospital   = random.choice(HOSPITALS)
    launch_ts  = random_timestamp(start_date, end_date)
    distance   = haversine_km(MUHANGA_LAT, MUHANGA_LON, hospital["lat"], hospital["lon"])
    # Flight duration: ~80 km/h cruise speed, round trip
    duration_min = round((distance * 2 / 80) * 60 + random.uniform(-3, 5), 1)
    weather    = random.choice(WEATHER_CONDITIONS)
    outcome    = random.choice(FLIGHT_OUTCOMES)
    if weather in ("Light Rain", "Foggy") and random.random() < 0.3:
        outcome = "Returned - Weather"

    battery_id = f"BAT-{random.randint(1000, 1999)}"
    drone_id   = f"ZIP-{random.randint(10, 30):02d}"
    payload_g  = random.randint(200, 1800)
    product    = random.choice(BLOOD_PRODUCTS)

    flights.append({
        "flight_id":        f"FLT-{flight_id:05d}",
        "drone_id":         drone_id,
        "battery_id":       battery_id,
        "launch_timestamp": launch_ts.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_min":     duration_min,
        "destination_hospital": hospital["name"],
        "destination_district": hospital["district"],
        "dest_lat":         hospital["lat"],
        "dest_lon":         hospital["lon"],
        "distance_km":      round(distance, 2),
        "payload_g":        payload_g,
        "blood_product":    product,
        "weather":          weather,
        "outcome":          outcome,
        "battery_pct_end":  random.randint(18, 72),
    })

with open("data/flights_summary.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=flights[0].keys())
    writer.writeheader()
    writer.writerows(flights)

print(f"✓ flights_summary.csv  — {len(flights)} flights")

# ── Generate flight_telemetry.csv ──────────────────────────────────────────────
telemetry_rows = []
# Only generate telemetry for a subset (first 100 flights) to keep file size sane
for flt in flights[:100]:
    launch = datetime.strptime(flt["launch_timestamp"], "%Y-%m-%d %H:%M:%S")
    dest_lat = flt["dest_lat"]
    dest_lon = flt["dest_lon"]
    total_steps = int(flt["duration_min"] * 2)   # sample every 30 seconds

    for step in range(total_steps + 1):
        progress = step / total_steps if total_steps > 0 else 1
        # Outbound then return
        if progress <= 0.5:
            t = progress * 2
            lat = MUHANGA_LAT + (dest_lat - MUHANGA_LAT) * t
            lon = MUHANGA_LON + (dest_lon - MUHANGA_LON) * t
        else:
            t = (progress - 0.5) * 2
            lat = dest_lat + (MUHANGA_LAT - dest_lat) * t
            lon = dest_lon + (MUHANGA_LON - dest_lon) * t

        # Add slight noise
        lat += random.gauss(0, 0.001)
        lon += random.gauss(0, 0.001)
        altitude_m = 120 + random.gauss(0, 3)
        speed_mps  = round(random.gauss(22, 1.5), 2)   # ~80 km/h
        timestamp  = launch + timedelta(seconds=step * 30)

        telemetry_rows.append({
            "flight_id":   flt["flight_id"],
            "timestamp":   timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "latitude":    round(lat, 6),
            "longitude":   round(lon, 6),
            "altitude_m":  round(altitude_m, 1),
            "speed_mps":   speed_mps,
            "step":        step,
        })

with open("data/flight_telemetry.csv", "w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=telemetry_rows[0].keys())
    writer.writeheader()
    writer.writerows(telemetry_rows)

print(f"✓ flight_telemetry.csv — {len(telemetry_rows):,} telemetry points (100 flights)")
print("\nData generation complete. Run pipeline/load_and_validate.py next.")

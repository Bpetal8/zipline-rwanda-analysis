"""
visualizations/generate_charts.py
-----------------------------------
Generates 4 charts from the SQLite database:
  1. Monthly flight volume & success rate
  2. Delivery success rate by weather condition
  3. Geospatial coverage map (flight paths from Muhanga)
  4. Fleet utilisation — flights per drone

Run:  python visualizations/generate_charts.py
Output: visualizations/*.png
"""

import sqlite3
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import numpy as np

DB_PATH   = "zipline_rwanda.db"
OUT_DIR   = "visualizations"
os.makedirs(OUT_DIR, exist_ok=True)

ACCENT    = "#1B4F72"
HIGHLIGHT = "#E74C3C"
SOFT      = "#AED6F1"
BG        = "#F8F9FA"

conn = sqlite3.connect(DB_PATH)

# ── Chart 1: Monthly flight volume & success rate ──────────────────────────────
print("Generating chart 1: Monthly volume & success rate...")

rows = conn.execute("""
    SELECT
        STRFTIME('%b', launch_timestamp)        AS month_label,
        STRFTIME('%Y-%m', launch_timestamp)     AS month_sort,
        COUNT(*)                                AS total,
        SUM(CASE WHEN outcome = 'Delivered' THEN 1 ELSE 0 END) AS delivered
    FROM flights_summary
    GROUP BY month_sort
    ORDER BY month_sort
""").fetchall()

months      = [r[0] for r in rows]
totals      = [int(r[2]) for r in rows]
delivered   = [int(r[3]) for r in rows]
success_pct = [d / t * 100 for d, t in zip(delivered, totals)]

fig, ax1 = plt.subplots(figsize=(12, 5))
fig.patch.set_facecolor(BG)
ax1.set_facecolor(BG)

x = np.arange(len(months))
bars = ax1.bar(x, totals, color=SOFT, width=0.6, label="Total Flights", zorder=2)
ax1.bar(x, delivered, color=ACCENT, width=0.6, label="Delivered", zorder=3)

ax2 = ax1.twinx()
ax2.plot(x, success_pct, color=HIGHLIGHT, marker="o", linewidth=2.5,
         markersize=6, label="Success Rate %", zorder=4)
ax2.set_ylim(60, 100)
ax2.set_ylabel("Delivery Success Rate (%)", color=HIGHLIGHT, fontsize=11)
ax2.tick_params(axis='y', labelcolor=HIGHLIGHT)

ax1.set_xticks(x)
ax1.set_xticklabels(months, fontsize=10)
ax1.set_xlabel("Month (2023)", fontsize=11)
ax1.set_ylabel("Number of Flights", fontsize=11)
ax1.set_title("Monthly Flight Volume & Delivery Success Rate\nMuhanga Distribution Centre, Rwanda — 2023",
              fontsize=13, fontweight="bold", pad=14)
ax1.grid(axis="y", linestyle="--", alpha=0.4, zorder=1)

handles = [
    mpatches.Patch(color=SOFT, label="Total Flights"),
    mpatches.Patch(color=ACCENT, label="Delivered"),
    mlines.Line2D([], [], color=HIGHLIGHT, marker="o", label="Success Rate %"),
]
ax1.legend(handles=handles, loc="lower left", fontsize=9)

plt.tight_layout()
plt.savefig(f"{OUT_DIR}/01_monthly_volume_success.png", dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ 01_monthly_volume_success.png")


# ── Chart 2: Success rate by weather ──────────────────────────────────────────
print("Generating chart 2: Success rate by weather...")

rows = conn.execute("""
    SELECT weather,
           COUNT(*) AS total,
           ROUND(SUM(CASE WHEN outcome='Delivered' THEN 1.0 ELSE 0 END) / COUNT(*) * 100, 1) AS success_pct
    FROM flights_summary
    GROUP BY weather
    ORDER BY success_pct DESC
""").fetchall()

weather_labels = [r[0] for r in rows]
pcts           = [float(r[2]) for r in rows]
colors         = [ACCENT if p >= 75 else HIGHLIGHT for p in pcts]

fig, ax = plt.subplots(figsize=(9, 5))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

bars = ax.barh(weather_labels, pcts, color=colors, height=0.55)
ax.set_xlim(0, 105)
ax.set_xlabel("Delivery Success Rate (%)", fontsize=11)
ax.set_title("Delivery Success Rate by Weather Condition\nMuhanga Distribution Centre, Rwanda — 2023",
             fontsize=13, fontweight="bold", pad=14)
ax.grid(axis="x", linestyle="--", alpha=0.4)

for bar, pct in zip(bars, pcts):
    ax.text(pct + 1, bar.get_y() + bar.get_height() / 2,
            f"{pct}%", va="center", fontsize=10, color="#333333")

ax.axvline(75, color=HIGHLIGHT, linestyle="--", linewidth=1.2, alpha=0.7, label="75% threshold")
ax.legend(fontsize=9)
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/02_success_by_weather.png", dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ 02_success_by_weather.png")


# ── Chart 3: Geospatial coverage map ──────────────────────────────────────────
print("Generating chart 3: Geospatial coverage map...")

MUHANGA_LAT, MUHANGA_LON = -2.0833, 29.6167

hospitals = conn.execute("""
    SELECT destination_hospital, destination_district,
           CAST(dest_lat AS REAL) AS lat,
           CAST(dest_lon AS REAL) AS lon,
           COUNT(*) AS flights,
           ROUND(SUM(CASE WHEN outcome='Delivered' THEN 1.0 ELSE 0 END) / COUNT(*) * 100, 1) AS success_pct
    FROM flights_summary
    GROUP BY destination_hospital
""").fetchall()

# Sample 80 telemetry paths for visual density
telemetry_flights = conn.execute("""
    SELECT DISTINCT flight_id FROM flight_telemetry LIMIT 80
""").fetchall()
flight_ids = [r[0] for r in telemetry_flights]

fig, ax = plt.subplots(figsize=(10, 10))
fig.patch.set_facecolor(BG)
ax.set_facecolor("#E8F4F8")

# Draw flight paths per flight
for fid in flight_ids:
    pts = conn.execute("""
        SELECT CAST(latitude AS REAL), CAST(longitude AS REAL)
        FROM flight_telemetry WHERE flight_id = ?
        ORDER BY CAST(step AS INTEGER)
    """, (fid,)).fetchall()
    lats = [p[0] for p in pts]
    lons = [p[1] for p in pts]
    ax.plot(lons, lats, color=ACCENT, alpha=0.08, linewidth=0.8, zorder=1)

# Draw hospitals sized by flight volume
for h in hospitals:
    name, district, lat, lon, flights, success = h
    size = 80 + flights * 0.4
    color = ACCENT if success >= 75 else HIGHLIGHT
    ax.scatter(lon, lat, s=size, color=color, zorder=4, edgecolors="white", linewidths=1.5)
    ax.annotate(name.replace(" District Hospital", "").replace(" Hospital", ""),
                (lon, lat), textcoords="offset points", xytext=(8, 4),
                fontsize=7.5, color="#222222", zorder=5)

# Draw Muhanga base
ax.scatter(MUHANGA_LON, MUHANGA_LAT, s=250, color="#E67E22", zorder=6,
           marker="*", edgecolors="white", linewidths=1.5)
ax.annotate("Muhanga DC\n(Launch Base)", (MUHANGA_LON, MUHANGA_LAT),
            textcoords="offset points", xytext=(8, -18),
            fontsize=9, fontweight="bold", color="#E67E22")

ax.set_xlabel("Longitude", fontsize=10)
ax.set_ylabel("Latitude", fontsize=10)
ax.set_title("Zipline Rwanda — Drone Delivery Coverage Map\nFlight Paths from Muhanga Distribution Centre (sample: 80 flights)",
             fontsize=13, fontweight="bold", pad=14)

legend_elements = [
    mpatches.Patch(color=ACCENT, label="Hospital (≥75% success)"),
    mpatches.Patch(color=HIGHLIGHT, label="Hospital (<75% success)"),
    mlines.Line2D([], [], color=ACCENT, alpha=0.4, linewidth=1.5, label="Flight path"),
    mlines.Line2D([], [], color="#E67E22", marker="*", markersize=12,
                  linewidth=0, label="Muhanga launch base"),
]
ax.legend(handles=legend_elements, loc="upper left", fontsize=9)
plt.tight_layout()
plt.savefig(f"{OUT_DIR}/03_coverage_map.png", dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ 03_coverage_map.png")


# ── Chart 4: Fleet utilisation ─────────────────────────────────────────────────
print("Generating chart 4: Fleet utilisation...")

rows = conn.execute("""
    SELECT drone_id, COUNT(*) AS flights,
           ROUND(AVG(CAST(duration_min AS REAL)), 1) AS avg_dur
    FROM flights_summary
    GROUP BY drone_id
    ORDER BY flights DESC
""").fetchall()

drone_ids  = [r[0] for r in rows]
flights    = [r[1] for r in rows]
avg_durs   = [r[2] for r in rows]

fig, ax = plt.subplots(figsize=(13, 5))
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

x = np.arange(len(drone_ids))
ax.bar(x, flights, color=ACCENT, width=0.6, zorder=2)
mean_flights = np.mean(flights)
ax.axhline(mean_flights, color=HIGHLIGHT, linestyle="--", linewidth=1.5,
           label=f"Fleet avg: {mean_flights:.1f} flights")

ax.set_xticks(x)
ax.set_xticklabels(drone_ids, rotation=45, ha="right", fontsize=8)
ax.set_ylabel("Number of Flights", fontsize=11)
ax.set_title("Fleet Utilisation — Flights per Drone\nMuhanga Distribution Centre, Rwanda — 2023",
             fontsize=13, fontweight="bold", pad=14)
ax.grid(axis="y", linestyle="--", alpha=0.4, zorder=1)
ax.legend(fontsize=10)

plt.tight_layout()
plt.savefig(f"{OUT_DIR}/04_fleet_utilisation.png", dpi=150, bbox_inches="tight")
plt.close()
print("  ✓ 04_fleet_utilisation.png")

conn.close()
print("\n✅  All 4 charts generated in ./visualizations/")

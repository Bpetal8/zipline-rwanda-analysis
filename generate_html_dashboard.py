"""
generate_html_dashboard.py
---------------------------
Generates a fully self-contained HTML dashboard with charts embedded as
base64 PNG images — no server, no CDN, no dependencies at runtime.
Just open docs/index.html in any browser.
 
Deploy to GitHub Pages by enabling Pages from the /docs folder in repo settings.
 
Run:  python generate_html_dashboard.py
Output: docs/index.html
"""
 
import sqlite3
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.lines as mlines
import numpy as np
import base64, io, os
 
DB_PATH = "zipline_rwanda.db"
OUT_DIR = "docs"
os.makedirs(OUT_DIR, exist_ok=True)
 
ACCENT = "#1B4F72"
RED    = "#E74C3C"
GREEN  = "#27AE60"
ORANGE = "#E67E22"
SOFT   = "#AED6F1"
BG     = "#F8F9FA"
 
# ── Load data ──────────────────────────────────────────────────────────────────
conn = sqlite3.connect(DB_PATH)
flights   = pd.read_sql("SELECT * FROM flights_summary",  conn)
telemetry = pd.read_sql("SELECT * FROM flight_telemetry", conn)
conn.close()
 
flights["distance_km"]      = flights["distance_km"].astype(float)
flights["duration_min"]     = flights["duration_min"].astype(float)
flights["battery_pct_end"]  = flights["battery_pct_end"].astype(float)
flights["dest_lat"]         = flights["dest_lat"].astype(float)
flights["dest_lon"]         = flights["dest_lon"].astype(float)
flights["payload_g"]        = flights["payload_g"].astype(float)
flights["launch_timestamp"] = pd.to_datetime(flights["launch_timestamp"])
flights["month"]            = flights["launch_timestamp"].dt.strftime("%Y-%m")
flights["month_label"]      = flights["launch_timestamp"].dt.strftime("%b")
flights["delivered"]        = flights["outcome"] == "Delivered"
 
telemetry["latitude"]  = telemetry["latitude"].astype(float)
telemetry["longitude"] = telemetry["longitude"].astype(float)
telemetry["step"]      = telemetry["step"].astype(int)
 
# ── KPIs ───────────────────────────────────────────────────────────────────────
total     = len(flights)
delivered = int(flights["delivered"].sum())
success   = delivered / total * 100
avg_dist  = flights["distance_km"].mean()
avg_bat   = flights["battery_pct_end"].mean()
nulls     = int(flights.isnull().sum().sum())
dupes     = int(flights["flight_id"].duplicated().sum())
impossible= int((flights["duration_min"] < (flights["distance_km"]*2/80*60)-5).sum())
low_bat   = int((flights["battery_pct_end"] < 20).sum())
 
# ── Helper: fig to base64 PNG ──────────────────────────────────────────────────
def fig_to_b64(fig, dpi=130):
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    buf.seek(0)
    b64 = base64.b64encode(buf.read()).decode("utf-8")
    plt.close(fig)
    return f"data:image/png;base64,{b64}"
 
# ── Chart 1: Monthly trend ─────────────────────────────────────────────────────
monthly = flights.groupby("month").agg(
    total=("flight_id","count"), delivered=("delivered","sum")
).reset_index()
monthly["success_pct"] = monthly["delivered"] / monthly["total"] * 100
monthly["month_label"] = pd.to_datetime(monthly["month"]).dt.strftime("%b")
 
fig1, ax1 = plt.subplots(figsize=(11, 4.5))
fig1.patch.set_facecolor(BG); ax1.set_facecolor(BG)
x = np.arange(len(monthly))
ax1.bar(x, monthly["total"],     color=SOFT,   width=0.6, label="Total Flights", zorder=2)
ax1.bar(x, monthly["delivered"], color=ACCENT, width=0.6, label="Delivered",     zorder=3)
ax2 = ax1.twinx()
ax2.plot(x, monthly["success_pct"], color=RED, marker="o", linewidth=2.5,
         markersize=6, label="Success %", zorder=4)
ax2.set_ylim(60, 100); ax2.set_ylabel("Success Rate (%)", color=RED, fontsize=10)
ax2.tick_params(axis="y", labelcolor=RED)
ax1.set_xticks(x); ax1.set_xticklabels(monthly["month_label"], fontsize=9)
ax1.set_ylabel("Flights", fontsize=10)
ax1.set_title("Monthly Flight Volume & Delivery Success Rate", fontsize=12, fontweight="bold", pad=10)
ax1.grid(axis="y", linestyle="--", alpha=0.4, zorder=1)
handles = [mpatches.Patch(color=SOFT,label="Total"), mpatches.Patch(color=ACCENT,label="Delivered"),
           mlines.Line2D([],[],color=RED,marker="o",label="Success %")]
ax1.legend(handles=handles, loc="lower left", fontsize=8)
img1 = fig_to_b64(fig1)
print("  ✓ Chart 1: Monthly trend")
 
# ── Chart 2: Weather ───────────────────────────────────────────────────────────
wdf = flights.groupby("weather").agg(
    total=("flight_id","count"), delivered=("delivered","sum")
).reset_index()
wdf["success_pct"] = wdf["delivered"] / wdf["total"] * 100
wdf = wdf.sort_values("success_pct")
colors = [GREEN if p >= 75 else RED for p in wdf["success_pct"]]
 
fig2, ax = plt.subplots(figsize=(7, 4))
fig2.patch.set_facecolor(BG); ax.set_facecolor(BG)
bars = ax.barh(wdf["weather"], wdf["success_pct"], color=colors, height=0.5)
ax.set_xlim(0, 110); ax.set_xlabel("Success Rate (%)", fontsize=10)
ax.set_title("Success Rate by Weather Condition", fontsize=12, fontweight="bold", pad=10)
ax.grid(axis="x", linestyle="--", alpha=0.4)
for bar, pct in zip(bars, wdf["success_pct"]):
    ax.text(pct+1, bar.get_y()+bar.get_height()/2, f"{pct:.1f}%", va="center", fontsize=9)
ax.axvline(75, color=RED, linestyle="--", linewidth=1.2, alpha=0.6, label="75% threshold")
ax.legend(fontsize=8)
img2 = fig_to_b64(fig2)
print("  ✓ Chart 2: Weather")
 
# ── Chart 3: Coverage map ──────────────────────────────────────────────────────
MUHANGA_LAT, MUHANGA_LON = -2.0833, 29.6167
hdf = flights.groupby(["destination_hospital","destination_district",
                        "dest_lat","dest_lon"]).agg(
    total=("flight_id","count"), delivered=("delivered","sum")
).reset_index()
hdf["success_pct"] = hdf["delivered"] / hdf["total"] * 100
 
fig3, ax = plt.subplots(figsize=(9, 9))
fig3.patch.set_facecolor(BG); ax.set_facecolor("#E8F4F8")
sample_ids = telemetry["flight_id"].unique()[:80]
for fid in sample_ids:
    pts = telemetry[telemetry["flight_id"]==fid].sort_values("step")
    ax.plot(pts["longitude"], pts["latitude"], color=ACCENT, alpha=0.08, linewidth=0.8, zorder=1)
for _, h in hdf.iterrows():
    size = 80 + h["total"] * 0.4
    color = ACCENT if h["success_pct"] >= 75 else RED
    ax.scatter(h["dest_lon"], h["dest_lat"], s=size, color=color,
               zorder=4, edgecolors="white", linewidths=1.5)
    label = h["destination_hospital"].replace(" District Hospital","").replace(" Hospital","")
    ax.annotate(label, (h["dest_lon"], h["dest_lat"]),
                textcoords="offset points", xytext=(8,4), fontsize=8, color="#222", zorder=5)
ax.scatter(MUHANGA_LON, MUHANGA_LAT, s=250, color=ORANGE, zorder=6,
           marker="*", edgecolors="white", linewidths=1.5)
ax.annotate("Muhanga DC\n(Launch Base)", (MUHANGA_LON, MUHANGA_LAT),
            textcoords="offset points", xytext=(8,-18),
            fontsize=9, fontweight="bold", color=ORANGE)
ax.set_xlabel("Longitude", fontsize=9); ax.set_ylabel("Latitude", fontsize=9)
ax.set_title("Delivery Coverage Map — Muhanga Distribution Centre\n(sample: 80 flight paths)",
             fontsize=12, fontweight="bold", pad=10)
legend_els = [
    mpatches.Patch(color=ACCENT, label="Hospital (>=75% success)"),
    mpatches.Patch(color=RED,    label="Hospital (<75% success)"),
    mlines.Line2D([],[],color=ACCENT,alpha=0.4,linewidth=1.5,label="Flight path"),
    mlines.Line2D([],[],color=ORANGE,marker="*",markersize=12,linewidth=0,label="Muhanga base")
]
ax.legend(handles=legend_els, loc="upper left", fontsize=8)
img3 = fig_to_b64(fig3)
print("  ✓ Chart 3: Coverage map")
 
# ── Chart 4: Fleet ─────────────────────────────────────────────────────────────
fleet = flights.groupby("drone_id")["flight_id"].count().reset_index()
fleet.columns = ["drone_id","flights"]
fleet = fleet.sort_values("flights", ascending=False)
 
fig4, ax = plt.subplots(figsize=(12, 4))
fig4.patch.set_facecolor(BG); ax.set_facecolor(BG)
ax.bar(fleet["drone_id"], fleet["flights"], color=ACCENT, width=0.6, zorder=2)
avg = fleet["flights"].mean()
ax.axhline(avg, color=RED, linestyle="--", linewidth=1.5, label=f"Fleet avg: {avg:.0f}")
ax.set_xticks(range(len(fleet)))
ax.set_xticklabels(fleet["drone_id"], rotation=45, ha="right", fontsize=8)
ax.set_ylabel("Flights", fontsize=10)
ax.set_title("Fleet Utilisation — Flights per Drone", fontsize=12, fontweight="bold", pad=10)
ax.grid(axis="y", linestyle="--", alpha=0.4, zorder=1)
ax.legend(fontsize=9)
img4 = fig_to_b64(fig4)
print("  ✓ Chart 4: Fleet")
 
# ── QA card helper ─────────────────────────────────────────────────────────────
def qa_card(label, value, is_good):
    badge_cls = "badge-pass" if is_good else "badge-fail"
    val_cls   = "pass"       if is_good else "fail"
    badge_txt = "Clean"      if is_good else "Review"
    icon      = "✓"          if is_good else "⚠"
    return f"""<div class="qa">
      <div class="label">{label}</div>
      <div class="value {val_cls}">{value}</div>
      <div class="badge {badge_cls}">{icon} {badge_txt}</div>
    </div>"""
 
# ── Build HTML ─────────────────────────────────────────────────────────────────
html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1.0"/>
<title>Zipline Rwanda — Flight Operations Dashboard</title>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:#F0F4F8;color:#222}}
.header{{background:{ACCENT};color:white;padding:28px 40px 20px}}
.header h1{{font-size:1.7rem;font-weight:700}}
.header p{{font-size:.9rem;opacity:.8;margin-top:4px}}
.header a{{color:#AED6F1;text-decoration:none}}
.container{{max-width:1300px;margin:0 auto;padding:28px 24px}}
.kpi-row{{display:grid;grid-template-columns:repeat(5,1fr);gap:16px;margin-bottom:24px}}
.kpi{{background:white;border-radius:10px;padding:20px 16px;box-shadow:0 1px 4px rgba(0,0,0,.08);border-left:4px solid {ACCENT}}}
.kpi .label{{font-size:.75rem;color:#777;text-transform:uppercase;letter-spacing:.04em}}
.kpi .value{{font-size:1.7rem;font-weight:700;color:{ACCENT};margin:4px 0 2px}}
.kpi .sub{{font-size:.75rem;color:#aaa}}
.row{{display:grid;gap:20px;margin-bottom:20px}}
.row-2{{grid-template-columns:3fr 2fr}}
.row-full{{grid-template-columns:1fr}}
.card{{background:white;border-radius:10px;padding:20px;box-shadow:0 1px 4px rgba(0,0,0,.08)}}
.card img{{width:100%;height:auto;border-radius:6px}}
.qa-row{{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:28px}}
.qa{{background:white;border-radius:10px;padding:16px;box-shadow:0 1px 4px rgba(0,0,0,.08);text-align:center}}
.qa .label{{font-size:.75rem;color:#777;text-transform:uppercase;letter-spacing:.03em}}
.qa .value{{font-size:2rem;font-weight:700;margin:6px 0 4px}}
.qa .badge{{font-size:.8rem;padding:3px 12px;border-radius:20px;display:inline-block}}
.pass{{color:{GREEN}}}.fail{{color:{RED}}}
.badge-pass{{background:#EAFAF1;color:{GREEN}}}.badge-fail{{background:#FDEDEC;color:{RED}}}
.section-title{{font-size:1rem;font-weight:700;color:{ACCENT};margin-bottom:16px;padding-bottom:8px;border-bottom:2px solid {ACCENT}}}
footer{{text-align:center;padding:28px;font-size:.82rem;color:#aaa}}
footer a{{color:{ACCENT};text-decoration:none}}
@media(max-width:900px){{
  .kpi-row,.qa-row{{grid-template-columns:repeat(2,1fr)}}
  .row-2{{grid-template-columns:1fr}}
}}
</style>
</head>
<body>
 
<div class="header">
  <h1>✈️ Zipline Rwanda — Flight Operations Dashboard</h1>
  <p>Muhanga Distribution Centre &nbsp;·&nbsp; 2023 &nbsp;·&nbsp;
     Built by <a href="https://www.linkedin.com/in/kevin-kayitare-2b3b16327/">Kevin Kayitare</a>
     &nbsp;·&nbsp; <a href="https://github.com/Bpetal8">github.com/Bpetal8</a>
  </p>
</div>
 
<div class="container">
 
  <div class="kpi-row">
    <div class="kpi"><div class="label">Total Flights</div><div class="value">{total:,}</div><div class="sub">Jan – Dec 2023</div></div>
    <div class="kpi"><div class="label">Deliveries</div><div class="value">{delivered:,}</div><div class="sub">Successful drops</div></div>
    <div class="kpi"><div class="label">Success Rate</div><div class="value">{success:.1f}%</div><div class="sub">vs 80% target</div></div>
    <div class="kpi"><div class="label">Avg Distance</div><div class="value">{avg_dist:.1f} km</div><div class="sub">Per flight</div></div>
    <div class="kpi"><div class="label">Avg Battery at Land</div><div class="value">{avg_bat:.1f}%</div><div class="sub">Remaining on return</div></div>
  </div>
 
  <div class="row row-2">
    <div class="card"><img src="{img1}" alt="Monthly trend"/></div>
    <div class="card"><img src="{img2}" alt="Weather impact"/></div>
  </div>
 
  <div class="row row-full">
    <div class="card"><img src="{img3}" alt="Coverage map"/></div>
  </div>
 
  <div class="row row-full">
    <div class="card"><img src="{img4}" alt="Fleet utilisation"/></div>
  </div>
 
  <div class="section-title">🔍 Data Quality Checks</div>
  <div class="qa-row">
    {qa_card("Missing Fields",         nulls,      nulls == 0)}
    {qa_card("Duplicate IDs",          dupes,      dupes == 0)}
    {qa_card("Impossible Durations",   impossible, impossible == 0)}
    {qa_card("Critical Battery Lands", low_bat,    low_bat == 0)}
  </div>
 
</div>
 
<footer>
  Built by <a href="https://www.linkedin.com/in/kevin-kayitare-2b3b16327/">Kevin Kayitare</a>
  &nbsp;·&nbsp; Kigali, Rwanda &nbsp;·&nbsp;
  <a href="https://github.com/Bpetal8">github.com/Bpetal8</a>
</footer>
</body>
</html>"""
 
out = os.path.join(OUT_DIR, "index.html")
with open(out, "w", encoding="utf-8") as f:
    f.write(html)
 
print(f"\n  HTML dashboard generated → {out}")
print(f"   Open locally : double-click docs/index.html in your browser")
print(f"   Deploy online: push repo → GitHub Settings → Pages → Source: /docs folder")
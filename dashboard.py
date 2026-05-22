"""
dashboard.py
-------------
Streamlit interactive dashboard for Zipline Rwanda flight operations analysis.
 
Run:  streamlit run dashboard.py
"""
 
import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
 
# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Zipline Rwanda — Flight Operations Dashboard",
    page_icon="✈️",
    layout="wide"
)
 
ACCENT  = "#1B4F72"
RED     = "#E74C3C"
GREEN   = "#27AE60"
ORANGE  = "#E67E22"
 
# ── Load data ──────────────────────────────────────────────────────────────────
DB_PATH = "zipline_rwanda.db"
 
@st.cache_data
def load_data():
    if not os.path.exists(DB_PATH):
        return None, None
    conn = sqlite3.connect(DB_PATH)
    flights    = pd.read_sql("SELECT * FROM flights_summary",  conn)
    telemetry  = pd.read_sql("SELECT * FROM flight_telemetry", conn)
    conn.close()
 
    # Type conversions
    flights["distance_km"]     = flights["distance_km"].astype(float)
    flights["duration_min"]    = flights["duration_min"].astype(float)
    flights["payload_g"]       = flights["payload_g"].astype(float)
    flights["battery_pct_end"] = flights["battery_pct_end"].astype(float)
    flights["dest_lat"]        = flights["dest_lat"].astype(float)
    flights["dest_lon"]        = flights["dest_lon"].astype(float)
    flights["launch_timestamp"] = pd.to_datetime(flights["launch_timestamp"])
    flights["month"]           = flights["launch_timestamp"].dt.strftime("%Y-%m")
    flights["month_label"]     = flights["launch_timestamp"].dt.strftime("%b")
    flights["hour"]            = flights["launch_timestamp"].dt.hour
    flights["delivered"]       = flights["outcome"] == "Delivered"
 
    telemetry["latitude"]  = telemetry["latitude"].astype(float)
    telemetry["longitude"] = telemetry["longitude"].astype(float)
    telemetry["speed_mps"] = telemetry["speed_mps"].astype(float)
    telemetry["altitude_m"]= telemetry["altitude_m"].astype(float)
    telemetry["step"]      = telemetry["step"].astype(int)
 
    return flights, telemetry
 
flights, telemetry = load_data()
 
if flights is None:
    st.error("Database not found. Please run the pipeline first: `python pipeline/load_and_validate.py`")
    st.stop()
 
# ── Sidebar filters ────────────────────────────────────────────────────────────
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/4/45/Flag_of_Rwanda.svg/320px-Flag_of_Rwanda.svg.png", width=120)
st.sidebar.title("Filters")
 
all_weather   = sorted(flights["weather"].unique())
all_districts = sorted(flights["destination_district"].unique())
all_products  = sorted(flights["blood_product"].unique())
 
sel_weather   = st.sidebar.multiselect("Weather condition", all_weather,   default=all_weather)
sel_districts = st.sidebar.multiselect("District",          all_districts, default=all_districts)
sel_products  = st.sidebar.multiselect("Blood product",     all_products,  default=all_products)
 
df = flights[
    flights["weather"].isin(sel_weather) &
    flights["destination_district"].isin(sel_districts) &
    flights["blood_product"].isin(sel_products)
]
 
# ── Header ─────────────────────────────────────────────────────────────────────
st.title("✈️ Zipline Rwanda — Flight Operations Dashboard")
st.caption("Muhanga Distribution Centre · 2023 · Built by Kevin Kayitare")
st.divider()
 
# ── KPI row ────────────────────────────────────────────────────────────────────
total      = len(df)
delivered  = df["delivered"].sum()
success    = delivered / total * 100 if total else 0
avg_dist   = df["distance_km"].mean()
avg_bat    = df["battery_pct_end"].mean()
 
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Flights",       f"{total:,}")
k2.metric("Deliveries",          f"{int(delivered):,}")
k3.metric("Success Rate",        f"{success:.1f}%",  delta=f"{success-80:.1f}% vs 80% target")
k4.metric("Avg Distance",        f"{avg_dist:.1f} km")
k5.metric("Avg Battery at Land", f"{avg_bat:.1f}%")
 
st.divider()
 
# ── Row 1: Monthly trend + Weather impact ──────────────────────────────────────
col1, col2 = st.columns([3, 2])
 
with col1:
    st.subheader("Monthly Flight Volume & Success Rate")
    monthly = df.groupby("month").agg(
        total=("flight_id", "count"),
        delivered=("delivered", "sum")
    ).reset_index()
    monthly["success_pct"] = monthly["delivered"] / monthly["total"] * 100
    monthly["month_label"] = pd.to_datetime(monthly["month"]).dt.strftime("%b")
 
    fig = make_subplots(specs=[[{"secondary_y": True}]])
    fig.add_trace(go.Bar(x=monthly["month_label"], y=monthly["total"],
                         name="Total Flights", marker_color="#AED6F1", opacity=0.8), secondary_y=False)
    fig.add_trace(go.Bar(x=monthly["month_label"], y=monthly["delivered"],
                         name="Delivered", marker_color=ACCENT, opacity=0.9), secondary_y=False)
    fig.add_trace(go.Scatter(x=monthly["month_label"], y=monthly["success_pct"],
                             name="Success %", mode="lines+markers",
                             line=dict(color=RED, width=2.5),
                             marker=dict(size=7)), secondary_y=True)
    fig.update_layout(height=350, margin=dict(t=10, b=10),
                      legend=dict(orientation="h", y=-0.2),
                      barmode="overlay", plot_bgcolor="#F8F9FA", paper_bgcolor="#F8F9FA")
    fig.update_yaxes(title_text="Flights", secondary_y=False)
    fig.update_yaxes(title_text="Success %", secondary_y=True, range=[60, 100])
    st.plotly_chart(fig, use_container_width=True)
 
with col2:
    st.subheader("Success Rate by Weather")
    weather_df = df.groupby("weather").agg(
        total=("flight_id", "count"),
        delivered=("delivered", "sum")
    ).reset_index()
    weather_df["success_pct"] = weather_df["delivered"] / weather_df["total"] * 100
    weather_df = weather_df.sort_values("success_pct", ascending=True)
    weather_df["color"] = weather_df["success_pct"].apply(lambda x: GREEN if x >= 75 else RED)
 
    fig2 = go.Figure(go.Bar(
        x=weather_df["success_pct"], y=weather_df["weather"],
        orientation="h",
        marker_color=weather_df["color"],
        text=weather_df["success_pct"].apply(lambda x: f"{x:.1f}%"),
        textposition="outside"
    ))
    fig2.update_layout(height=350, margin=dict(t=10, b=10, r=60),
                       xaxis=dict(range=[0, 110], title="Success Rate (%)"),
                       plot_bgcolor="#F8F9FA", paper_bgcolor="#F8F9FA")
    st.plotly_chart(fig2, use_container_width=True)
 
# ── Row 2: Coverage map + Fleet utilisation ────────────────────────────────────
col3, col4 = st.columns([3, 2])
 
with col3:
    st.subheader("Delivery Coverage Map")
    MUHANGA_LAT, MUHANGA_LON = -2.0833, 29.6167
 
    hospital_df = df.groupby(["destination_hospital", "destination_district",
                               "dest_lat", "dest_lon"]).agg(
        total=("flight_id", "count"),
        delivered=("delivered", "sum")
    ).reset_index()
    hospital_df["success_pct"] = hospital_df["delivered"] / hospital_df["total"] * 100
    hospital_df["color"] = hospital_df["success_pct"].apply(
        lambda x: GREEN if x >= 75 else RED)
 
    fig3 = go.Figure()
 
    # Flight path lines (sample 60)
    sample_flights = telemetry["flight_id"].unique()[:60]
    for fid in sample_flights:
        pts = telemetry[telemetry["flight_id"] == fid].sort_values("step")
        fig3.add_trace(go.Scattermapbox(
            lat=pts["latitude"], lon=pts["longitude"],
            mode="lines",
            line=dict(width=0.8, color="rgba(27,79,114,0.15)"),
            showlegend=False, hoverinfo="skip"
        ))
 
    # Hospitals
    fig3.add_trace(go.Scattermapbox(
        lat=hospital_df["dest_lat"], lon=hospital_df["dest_lon"],
        mode="markers+text",
        marker=dict(size=hospital_df["total"] / 8 + 12,
                    color=hospital_df["success_pct"], colorscale="RdYlGn",
                    cmin=60, cmax=100, showscale=True,
                    colorbar=dict(title="Success %", x=1.0)),
        text=hospital_df["destination_hospital"].str.replace(" District Hospital","").str.replace(" Hospital",""),
        textposition="top right",
        customdata=hospital_df[["total","success_pct","destination_district"]].values,
        hovertemplate="<b>%{text}</b><br>District: %{customdata[2]}<br>Flights: %{customdata[0]}<br>Success: %{customdata[1]:.1f}%<extra></extra>",
        name="Hospitals"
    ))
 
    # Muhanga base
    fig3.add_trace(go.Scattermapbox(
        lat=[MUHANGA_LAT], lon=[MUHANGA_LON],
        mode="markers+text",
        marker=dict(size=20, color=ORANGE, symbol="star"),
        text=["Muhanga DC"], textposition="top right",
        name="Launch Base"
    ))
 
    fig3.update_layout(
        mapbox=dict(style="carto-positron", center=dict(lat=-2.1, lon=29.6), zoom=7),
        height=420, margin=dict(t=0, b=0, l=0, r=0),
        legend=dict(orientation="h", y=-0.05)
    )
    st.plotly_chart(fig3, use_container_width=True)
 
with col4:
    st.subheader("Fleet Utilisation")
    fleet_df = df.groupby("drone_id").agg(
        flights=("flight_id", "count"),
        avg_duration=("duration_min", "mean"),
        min_battery=("battery_pct_end", "min")
    ).reset_index().sort_values("flights", ascending=False)
 
    fig4 = go.Figure(go.Bar(
        x=fleet_df["drone_id"], y=fleet_df["flights"],
        marker_color=ACCENT,
        hovertemplate="<b>%{x}</b><br>Flights: %{y}<extra></extra>"
    ))
    avg_line = fleet_df["flights"].mean()
    fig4.add_hline(y=avg_line, line_dash="dash", line_color=RED,
                   annotation_text=f"Fleet avg: {avg_line:.0f}")
    fig4.update_layout(height=200, margin=dict(t=10, b=10),
                       xaxis=dict(tickangle=45, tickfont=dict(size=9)),
                       plot_bgcolor="#F8F9FA", paper_bgcolor="#F8F9FA")
    st.plotly_chart(fig4, use_container_width=True)
 
    st.subheader("Blood Product Distribution")
    product_df = df.groupby("blood_product")["flight_id"].count().reset_index()
    product_df.columns = ["product", "flights"]
    fig5 = go.Figure(go.Pie(
        labels=product_df["product"], values=product_df["flights"],
        hole=0.45, marker_colors=[ACCENT, "#2E86C1", "#AED6F1", "#85C1E9"]
    ))
    fig5.update_layout(height=200, margin=dict(t=10, b=10, l=10, r=10),
                       showlegend=True,
                       legend=dict(font=dict(size=10), orientation="v"))
    st.plotly_chart(fig5, use_container_width=True)
 
# ── Row 3: QA / Data quality ───────────────────────────────────────────────────
st.divider()
st.subheader("🔍 Data Quality Checks")
 
qa1, qa2, qa3, qa4 = st.columns(4)
 
nulls      = flights.isnull().sum().sum()
dupes      = flights["flight_id"].duplicated().sum()
impossible = (flights["duration_min"] < (flights["distance_km"] * 2 / 80 * 60) - 5).sum()
low_bat    = (flights["battery_pct_end"] < 20).sum()
 
qa1.metric("Missing Fields",          f"{int(nulls)}",      delta="✓ Clean" if nulls == 0 else "⚠ Review", delta_color="normal" if nulls == 0 else "inverse")
qa2.metric("Duplicate Flight IDs",    f"{int(dupes)}",      delta="✓ Clean" if dupes == 0 else "⚠ Review", delta_color="normal" if dupes == 0 else "inverse")
qa3.metric("Impossible Durations",    f"{int(impossible)}", delta="✓ Clean" if impossible == 0 else "⚠ Review", delta_color="normal" if impossible == 0 else "inverse")
qa4.metric("Critical Battery Lands",  f"{int(low_bat)}",    delta="⚠ Review" if low_bat > 0 else "✓ Clean", delta_color="inverse" if low_bat > 0 else "normal")
 
# Raw data explorer
with st.expander(" Explore raw flight data"):
    st.dataframe(df[[
        "flight_id","drone_id","launch_timestamp","destination_hospital",
        "destination_district","blood_product","distance_km","duration_min",
        "weather","outcome","battery_pct_end","payload_g"
    ]].sort_values("launch_timestamp", ascending=False), use_container_width=True)
 
st.caption("Built by Kevin Kayitare · Kigali, Rwanda · github.com/Bpetal8")
"""
pipeline/load_and_validate.py
------------------------------
Loads raw CSV data into a SQLite database, runs data quality checks,
and outputs a structured QA report — simulating a real data ops validation
workflow as used in logistics/annotation pipelines.

Run:  python pipeline/load_and_validate.py
Output:
  - zipline_rwanda.db         (SQLite database)
  - pipeline/qa_report.txt    (human-readable QA report)
"""

import sqlite3
import csv
import os
from datetime import datetime

DB_PATH     = "zipline_rwanda.db"
REPORT_PATH = "pipeline/qa_report.txt"

# ── Helpers ────────────────────────────────────────────────────────────────────

def load_csv_to_table(conn, csv_path, table_name):
    """Load a CSV file into a SQLite table, auto-detecting schema."""
    with open(csv_path, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows   = list(reader)
        if not rows:
            print(f"  ⚠  {csv_path} is empty — skipping.")
            return 0
        columns = rows[0].keys()

    # Drop and recreate table
    conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    col_defs = ", ".join(f'"{col}" TEXT' for col in columns)
    conn.execute(f"CREATE TABLE {table_name} ({col_defs})")

    placeholders = ", ".join("?" for _ in columns)
    conn.executemany(
        f"INSERT INTO {table_name} VALUES ({placeholders})",
        [tuple(row[col] for col in columns) for row in rows]
    )
    conn.commit()
    return len(rows)


def run_check(conn, label, sql):
    """Run a QA check query and return (label, result_rows)."""
    cursor = conn.execute(sql)
    rows   = cursor.fetchall()
    cols   = [d[0] for d in cursor.description]
    return {"label": label, "columns": cols, "rows": rows}


def format_table(columns, rows, max_rows=20):
    """Format query results as a plain-text table."""
    if not rows:
        return "  (no rows returned)\n"
    col_widths = [max(len(str(c)), max((len(str(r[i])) for r in rows), default=0))
                  for i, c in enumerate(columns)]
    sep  = "  " + "-+-".join("-" * w for w in col_widths)
    header = "  " + " | ".join(str(c).ljust(col_widths[i]) for i, c in enumerate(columns))
    lines  = [header, sep]
    for row in rows[:max_rows]:
        lines.append("  " + " | ".join(str(v).ljust(col_widths[i]) for i, v in enumerate(row)))
    if len(rows) > max_rows:
        lines.append(f"  ... ({len(rows) - max_rows} more rows)")
    return "\n".join(lines) + "\n"


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    print("=" * 60)
    print("  Zipline Rwanda — Data Pipeline & QA Validator")
    print("=" * 60)

    # 1. Load CSVs ──────────────────────────────────────────────
    print("\n[1/3] Loading CSVs into SQLite...")
    conn = sqlite3.connect(DB_PATH)

    n_flights    = load_csv_to_table(conn, "data/flights_summary.csv",   "flights_summary")
    n_telemetry  = load_csv_to_table(conn, "data/flight_telemetry.csv",  "flight_telemetry")

    print(f"  ✓ flights_summary  : {n_flights:,} rows")
    print(f"  ✓ flight_telemetry : {n_telemetry:,} rows")

    # 2. Run QA checks ──────────────────────────────────────────
    print("\n[2/3] Running data quality checks...")

    checks = [
        run_check(conn, "Null / missing fields audit", """
            SELECT
                COUNT(*)                                               AS total_flights,
                SUM(CASE WHEN drone_id         IS NULL THEN 1 ELSE 0 END) AS missing_drone_id,
                SUM(CASE WHEN battery_id       IS NULL THEN 1 ELSE 0 END) AS missing_battery_id,
                SUM(CASE WHEN launch_timestamp IS NULL THEN 1 ELSE 0 END) AS missing_timestamp,
                SUM(CASE WHEN outcome          IS NULL THEN 1 ELSE 0 END) AS missing_outcome
            FROM flights_summary
        """),

        run_check(conn, "Duplicate flight IDs", """
            SELECT flight_id, COUNT(*) AS occurrences
            FROM flights_summary
            GROUP BY flight_id
            HAVING COUNT(*) > 1
        """),

        run_check(conn, "Impossible flight durations (too fast for distance)", """
            SELECT flight_id, distance_km, duration_min,
                   ROUND(CAST(distance_km AS REAL) * 2 / 80 * 60, 1) AS min_expected_min
            FROM flights_summary
            WHERE CAST(duration_min AS REAL) < (CAST(distance_km AS REAL) * 2 / 80 * 60) - 5
            ORDER BY CAST(duration_min AS REAL) ASC
            LIMIT 10
        """),

        run_check(conn, "Battery critical landings (<20% remaining)", """
            SELECT flight_id, drone_id, battery_id,
                   distance_km, battery_pct_end, outcome
            FROM flights_summary
            WHERE CAST(battery_pct_end AS REAL) < 20
            ORDER BY CAST(battery_pct_end AS REAL) ASC
            LIMIT 10
        """),

        run_check(conn, "Delivery outcome breakdown", """
            SELECT outcome, COUNT(*) AS total,
                   ROUND(COUNT(*) * 100.0 / (SELECT COUNT(*) FROM flights_summary), 1) AS pct
            FROM flights_summary
            GROUP BY outcome
            ORDER BY total DESC
        """),

        run_check(conn, "Success rate by weather condition", """
            SELECT weather, COUNT(*) AS total_flights,
                   SUM(CASE WHEN outcome = 'Delivered' THEN 1 ELSE 0 END) AS delivered,
                   ROUND(SUM(CASE WHEN outcome = 'Delivered' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS success_pct
            FROM flights_summary
            GROUP BY weather
            ORDER BY success_pct DESC
        """),

        run_check(conn, "Coverage — flights per destination hospital", """
            SELECT destination_hospital, destination_district,
                   COUNT(*) AS total_flights,
                   SUM(CASE WHEN outcome = 'Delivered' THEN 1 ELSE 0 END) AS delivered,
                   ROUND(AVG(CAST(distance_km AS REAL)), 1) AS avg_km
            FROM flights_summary
            GROUP BY destination_hospital
            ORDER BY total_flights DESC
        """),

        run_check(conn, "Telemetry completeness", """
            SELECT
                (SELECT COUNT(DISTINCT flight_id) FROM flight_telemetry) AS flights_with_telemetry,
                (SELECT COUNT(*) FROM flights_summary)                   AS total_flights,
                (SELECT COUNT(*) FROM flight_telemetry)                  AS total_points
        """),

        run_check(conn, "Speed anomalies in telemetry (>35 m/s)", """
            SELECT flight_id, timestamp, speed_mps, altitude_m
            FROM flight_telemetry
            WHERE CAST(speed_mps AS REAL) > 35
            ORDER BY CAST(speed_mps AS REAL) DESC
            LIMIT 10
        """),
    ]

    # Determine pass/fail for each check
    EXPECTED_EMPTY = {
        "Duplicate flight IDs",
        "Impossible flight durations (too fast for distance)",
        "Speed anomalies in telemetry (>35 m/s)",
    }

    results = []
    for chk in checks:
        if chk["label"] in EXPECTED_EMPTY:
            status = "✓ PASS" if not chk["rows"] else "✗ FLAG"
        else:
            status = "✓ PASS"   # informational checks always pass
        results.append({**chk, "status": status})
        print(f"  {status}  {chk['label']}")

    # 3. Write QA report ────────────────────────────────────────
    print("\n[3/3] Writing QA report...")
    os.makedirs("pipeline", exist_ok=True)

    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("  ZIPLINE RWANDA — DATA QUALITY & OPERATIONS REPORT\n")
        f.write(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"  Source:    Muhanga Distribution Centre, Rwanda\n")
        f.write(f"  Dataset:   {n_flights:,} flights  |  {n_telemetry:,} telemetry points\n")
        f.write("=" * 70 + "\n\n")

        passed = sum(1 for r in results if "PASS" in r["status"])
        flagged = len(results) - passed
        f.write(f"SUMMARY: {passed}/{len(results)} checks passed")
        if flagged:
            f.write(f"  |  {flagged} check(s) flagged for review\n\n")
        else:
            f.write("  — no anomalies detected\n\n")

        for r in results:
            f.write("-" * 70 + "\n")
            f.write(f"  [{r['status']}]  {r['label']}\n")
            f.write("-" * 70 + "\n")
            f.write(format_table(r["columns"], r["rows"]))
            f.write("\n")

    print(f"  ✓ Report written → {REPORT_PATH}")
    print(f"\n✅  Pipeline complete.")
    print(f"   Database : {DB_PATH}")
    print(f"   Report   : {REPORT_PATH}")
    conn.close()


if __name__ == "__main__":
    main()

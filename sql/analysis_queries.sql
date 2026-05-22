-- =============================================================================
-- Zipline Rwanda Flight Analysis — SQL Queries
-- Database: SQLite (created by pipeline/load_and_validate.py)
-- Author:   Kevin Kayitare
-- Purpose:  Operational analysis of drone delivery patterns, coverage,
--           data quality, and fleet performance from Muhanga distribution centre
-- =============================================================================


-- =============================================================================
-- SECTION 1: DATA QUALITY CHECKS
-- These mirror real annotation/QA checks a TPM would enforce on incoming data
-- =============================================================================

-- 1a. Check for flights with missing or null critical fields
SELECT
    COUNT(*)                                              AS total_flights,
    SUM(CASE WHEN drone_id        IS NULL THEN 1 ELSE 0 END) AS missing_drone_id,
    SUM(CASE WHEN battery_id      IS NULL THEN 1 ELSE 0 END) AS missing_battery_id,
    SUM(CASE WHEN launch_timestamp IS NULL THEN 1 ELSE 0 END) AS missing_timestamp,
    SUM(CASE WHEN outcome         IS NULL THEN 1 ELSE 0 END) AS missing_outcome,
    SUM(CASE WHEN distance_km     IS NULL THEN 1 ELSE 0 END) AS missing_distance
FROM flights_summary;


-- 1b. Flag physically impossible flights (duration too short for distance)
-- A drone at 80 km/h cannot cover a round trip faster than distance*2/80*60 mins
SELECT
    flight_id,
    distance_km,
    duration_min,
    ROUND(distance_km * 2 / 80 * 60, 1) AS min_expected_duration_min,
    outcome
FROM flights_summary
WHERE duration_min < (distance_km * 2 / 80 * 60) - 5   -- 5 min tolerance
ORDER BY duration_min ASC
LIMIT 20;


-- 1c. Battery anomaly — flights landing with critically low battery (<20%)
SELECT
    flight_id,
    drone_id,
    battery_id,
    distance_km,
    battery_pct_end,
    outcome
FROM flights_summary
WHERE battery_pct_end < 20
ORDER BY battery_pct_end ASC;


-- 1d. Duplicate flight ID check
SELECT flight_id, COUNT(*) AS occurrences
FROM flights_summary
GROUP BY flight_id
HAVING COUNT(*) > 1;


-- =============================================================================
-- SECTION 2: DELIVERY PERFORMANCE
-- =============================================================================

-- 2a. Overall outcome breakdown
SELECT
    outcome,
    COUNT(*)                                    AS total,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 1) AS pct
FROM flights_summary
GROUP BY outcome
ORDER BY total DESC;


-- 2b. Monthly delivery volume and success rate
SELECT
    STRFTIME('%Y-%m', launch_timestamp)         AS month,
    COUNT(*)                                    AS total_flights,
    SUM(CASE WHEN outcome = 'Delivered' THEN 1 ELSE 0 END) AS successful,
    ROUND(SUM(CASE WHEN outcome = 'Delivered' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS success_rate_pct
FROM flights_summary
GROUP BY month
ORDER BY month;


-- 2c. Delivery success rate by weather condition
SELECT
    weather,
    COUNT(*)                                    AS total_flights,
    SUM(CASE WHEN outcome = 'Delivered' THEN 1 ELSE 0 END) AS delivered,
    ROUND(SUM(CASE WHEN outcome = 'Delivered' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS success_rate_pct
FROM flights_summary
GROUP BY weather
ORDER BY success_rate_pct DESC;


-- 2d. Average flight duration vs expected (efficiency ratio)
SELECT
    destination_district,
    ROUND(AVG(distance_km), 1)                  AS avg_distance_km,
    ROUND(AVG(duration_min), 1)                 AS avg_actual_duration_min,
    ROUND(AVG(distance_km * 2 / 80 * 60), 1)   AS avg_expected_duration_min,
    ROUND(AVG(duration_min) / AVG(distance_km * 2 / 80 * 60), 2) AS efficiency_ratio
FROM flights_summary
GROUP BY destination_district
ORDER BY efficiency_ratio DESC;


-- =============================================================================
-- SECTION 3: COVERAGE ANALYSIS (GEOSPATIAL)
-- =============================================================================

-- 3a. Flights per destination hospital — coverage frequency
SELECT
    destination_hospital,
    destination_district,
    ROUND(AVG(distance_km), 1)  AS avg_distance_km,
    COUNT(*)                    AS total_flights,
    SUM(CASE WHEN outcome = 'Delivered' THEN 1 ELSE 0 END) AS deliveries,
    ROUND(AVG(payload_g), 0)    AS avg_payload_g
FROM flights_summary
GROUP BY destination_hospital, destination_district
ORDER BY total_flights DESC;


-- 3b. Blood product distribution by district
SELECT
    destination_district,
    blood_product,
    COUNT(*) AS flights,
    ROUND(AVG(payload_g), 0) AS avg_payload_g
FROM flights_summary
GROUP BY destination_district, blood_product
ORDER BY destination_district, flights DESC;


-- 3c. Districts with highest return (non-delivery) rates — coverage risk
SELECT
    destination_district,
    COUNT(*)  AS total_flights,
    SUM(CASE WHEN outcome != 'Delivered' THEN 1 ELSE 0 END) AS non_deliveries,
    ROUND(SUM(CASE WHEN outcome != 'Delivered' THEN 1 ELSE 0 END) * 100.0 / COUNT(*), 1) AS failure_rate_pct
FROM flights_summary
GROUP BY destination_district
ORDER BY failure_rate_pct DESC;


-- =============================================================================
-- SECTION 4: FLEET & BATTERY HEALTH
-- =============================================================================

-- 4a. Drone utilisation — flights per drone
SELECT
    drone_id,
    COUNT(*)                    AS total_flights,
    ROUND(AVG(duration_min), 1) AS avg_duration_min,
    ROUND(AVG(distance_km), 1)  AS avg_distance_km,
    MIN(battery_pct_end)        AS min_battery_pct_end
FROM flights_summary
GROUP BY drone_id
ORDER BY total_flights DESC;


-- 4b. Battery cycle health — batteries used most frequently
SELECT
    battery_id,
    COUNT(*)                    AS cycles,
    ROUND(AVG(battery_pct_end), 1) AS avg_end_pct,
    MIN(battery_pct_end)        AS min_end_pct
FROM flights_summary
GROUP BY battery_id
ORDER BY cycles DESC
LIMIT 20;


-- 4c. Peak operating hours (launch hour distribution)
SELECT
    CAST(STRFTIME('%H', launch_timestamp) AS INTEGER) AS launch_hour,
    COUNT(*) AS flights
FROM flights_summary
GROUP BY launch_hour
ORDER BY launch_hour;


-- =============================================================================
-- SECTION 5: TELEMETRY QUALITY (flight_telemetry table)
-- =============================================================================

-- 5a. Telemetry coverage — how many flights have telemetry records?
SELECT
    (SELECT COUNT(DISTINCT flight_id) FROM flight_telemetry) AS flights_with_telemetry,
    (SELECT COUNT(*) FROM flights_summary)                   AS total_flights,
    (SELECT COUNT(*) FROM flight_telemetry)                  AS total_telemetry_points;


-- 5b. Flag telemetry gaps — steps that jump more than 2 (missing 30-sec samples)
SELECT
    flight_id,
    step,
    LAG(step) OVER (PARTITION BY flight_id ORDER BY step) AS prev_step,
    step - LAG(step) OVER (PARTITION BY flight_id ORDER BY step) AS step_gap
FROM flight_telemetry
WHERE step - LAG(step) OVER (PARTITION BY flight_id ORDER BY step) > 2
ORDER BY step_gap DESC
LIMIT 20;


-- 5c. Speed anomalies in telemetry (drone exceeding 35 m/s = ~126 km/h)
SELECT
    flight_id,
    timestamp,
    step,
    speed_mps,
    altitude_m
FROM flight_telemetry
WHERE speed_mps > 35
ORDER BY speed_mps DESC
LIMIT 20;


-- 5d. Average telemetry points per flight (data completeness check)
SELECT
    ROUND(AVG(points), 1) AS avg_points_per_flight,
    MIN(points)           AS min_points,
    MAX(points)           AS max_points
FROM (
    SELECT flight_id, COUNT(*) AS points
    FROM flight_telemetry
    GROUP BY flight_id
);

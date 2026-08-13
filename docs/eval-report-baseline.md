# Evaluation report

_Generated 2026-08-13T22:44:16+00:00 · model `llama-3.1-8b-instant`_

Execution accuracy on a hand-written golden set: a generated query is
correct when its result set matches the reference query's result set.

| Metric | Value |
|--------|-------|
| Execution accuracy | **64%** |
| Valid SQL rate | 100% |
| Cases | 36 |
| Needed self-correction | 11 |
| Median latency | 4747 ms |
| p95 latency | 11240 ms |

## By category

| Category | Accuracy | Cases |
|----------|----------|-------|
| aggregation | 57% | 7 |
| counting | 100% | 4 |
| filtering | 75% | 4 |
| grouping | 100% | 4 |
| multi_step | 0% | 5 |
| ranking | 67% | 3 |
| ratio | 33% | 3 |
| time_series | 83% | 6 |

## By difficulty

| Difficulty | Accuracy | Cases |
|------------|----------|-------|
| easy | 86% | 14 |
| medium | 75% | 12 |
| hard | 20% | 10 |

## Failures (13)

### `agg-002` — What is the total revenue from all trips?

- **Why:** wrong result: expected 1 row(s) ['total_revenue'], got 1 row(s) ['total_revenue']
- **Expected:** `SELECT ROUND(SUM(total_amount), 2) AS total_revenue FROM taxi`
- **Generated:** `SELECT ROUND(AVG(total_amount), 2) AS total_revenue FROM taxi`

### `agg-004` — What is the median fare amount?

- **Why:** wrong result: expected 1 row(s) ['median_fare'], got 1 row(s) ['median_fare_amount']
- **Expected:** `SELECT MEDIAN(fare_amount) AS median_fare FROM taxi`
- **Generated:** `SELECT ROUND(AVG(fare_amount), 2) AS median_fare_amount FROM taxi`

### `agg-006` — What is the average trip duration in minutes?

- **Why:** wrong result: expected 1 row(s) ['avg_minutes'], got 1 row(s) ['avg_trip_duration']
- **Expected:** `SELECT ROUND(AVG(date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime)), 2) AS avg_minutes FROM taxi`
- **Generated:** `SELECT round(avg(date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime))) AS avg_trip_duration FROM taxi`

### `time-006` — How many trips started between 6am and 10am?

- **Why:** wrong result: expected 1 row(s) ['morning_trips'], got 1 row(s) ['num_trips']
- **Expected:** `SELECT COUNT(*) AS morning_trips FROM taxi WHERE HOUR(tpep_pickup_datetime) >= 6 AND HOUR(tpep_pickup_datetime) < 10`
- **Generated:** `SELECT COUNT(*) AS num_trips FROM taxi WHERE EXTRACT(HOUR FROM tpep_pickup_datetime) BETWEEN 6 AND 10`

### `rank-003` — What are the 10 busiest pickup and dropoff location pairs?

- **Why:** wrong result: expected 10 row(s) ['PULocationID', 'DOLocationID', 'trips'], got 10 row(s) ['pickup_location_id', 'dropoff_location_id', 'num_trips', 'avg_fare']
- **Expected:** `SELECT PULocationID, DOLocationID, COUNT(*) AS trips FROM taxi GROUP BY PULocationID, DOLocationID ORDER BY trips DESC LIMIT 10`
- **Generated:** `SELECT 
  PULocationID AS pickup_location_id, 
  DOLocationID AS dropoff_location_id, 
  COUNT(*) AS num_trips, 
  ROUND(AVG(total_amount), 2) AS avg_fare
FROM 
  taxi
WHERE 
  EXTRACT(YEAR FROM tpep_pickup_datetime) = 2024
GROUP BY 
  PULocationID, 
  DOLocationID
ORDER BY 
  num_trips DESC
LIMIT 10`

### `ratio-002` — What is the average tip as a percentage of the fare?

- **Why:** wrong result: expected 1 row(s) ['tip_pct'], got 1 row(s) ['avg_tip_percentage']
- **Expected:** `SELECT ROUND(100.0 * SUM(tip_amount) / SUM(fare_amount), 2) AS tip_pct FROM taxi WHERE fare_amount > 0`
- **Generated:** `SELECT ROUND(AVG(tip_amount / fare_amount) * 100, 2) AS avg_tip_percentage FROM taxi`

### `ratio-003` — What share of total revenue comes from tips?

- **Why:** wrong result: expected 1 row(s) ['tip_share'], got 1 row(s) ['tip_share']
- **Expected:** `SELECT ROUND(100.0 * SUM(tip_amount) / SUM(total_amount), 2) AS tip_share FROM taxi`
- **Generated:** `SELECT ROUND(AVG(tip_amount / total_amount) * 100, 2) AS tip_share FROM taxi`

### `filter-004` — What is the total amount collected in tolls?

- **Why:** wrong result: expected 1 row(s) ['total_tolls'], got 1 row(s) ['total_tolls_collected']
- **Expected:** `SELECT ROUND(SUM(tolls_amount), 2) AS total_tolls FROM taxi`
- **Generated:** `SELECT ROUND(AVG(tolls_amount), 2) AS total_tolls_collected FROM taxi`

### `multi-001` — For credit card trips, what is the average tip by passenger count?

- **Why:** wrong result: expected 10 row(s) ['passenger_count', 'avg_tip'], got 1 row(s) ['avg_tip_per_passenger']
- **Expected:** `SELECT passenger_count, ROUND(AVG(tip_amount), 2) AS avg_tip FROM taxi WHERE payment_type = 1 GROUP BY passenger_count ORDER BY passenger_count`
- **Generated:** `SELECT 
  ROUND(AVG(CASE WHEN payment_type = 1 THEN tip_amount ELSE 0 END) / ANY_VALUE(passenger_count), 2) AS avg_tip_per_passenger 
FROM taxi 
WHERE EXTRACT(YEAR FROM tpep_pickup_datetime) = 2024`

### `multi-002` — What is the average fare per mile?

- **Why:** wrong result: expected 1 row(s) ['fare_per_mile'], got 1 row(s) ['avg_fare_per_mile']
- **Expected:** `SELECT ROUND(SUM(fare_amount) / SUM(trip_distance), 2) AS fare_per_mile FROM taxi WHERE trip_distance > 0`
- **Generated:** `SELECT ROUND(AVG(fare_amount / trip_distance), 2) AS avg_fare_per_mile FROM taxi`

### `multi-003` — How many trips per hour on average during each month?

- **Why:** wrong result: expected 12 row(s) ['month', 'avg_trips_per_hour'], got 100 row(s) ['month', 'hour', 'avg_trips_per_hour']
- **Expected:** `SELECT MONTH(tpep_pickup_datetime) AS month, ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT date_trunc('hour', tpep_pickup_datetime)), 2) AS avg_trips_per_hour FROM taxi GROUP BY month ORDER BY month`
- **Generated:** `SELECT 
  EXTRACT(MONTH FROM tpep_pickup_datetime) AS month,
  EXTRACT(HOUR FROM tpep_pickup_datetime) AS hour,
  COUNT(*) / COUNT(DISTINCT EXTRACT(HOUR FROM tpep_pickup_datetime)) AS avg_trips_per_hour
FROM taxi
WHERE EXTRACT(YEAR FROM tpep_pickup_datetime) = 2024
GROUP BY EXTRACT(MONTH FROM tpep_pickup_datetime), EXTRACT(HOUR FROM tpep_pickup_datetime)
ORDER BY month, hour`

### `multi-004` — Compare the average total amount for cash versus credit card trips

- **Why:** wrong result: expected 2 row(s) ['payment_type', 'avg_total'], got 1 row(s) ['avg_cash_total', 'avg_credit_card_total']
- **Expected:** `SELECT payment_type, ROUND(AVG(total_amount), 2) AS avg_total FROM taxi WHERE payment_type IN (1, 2) GROUP BY payment_type ORDER BY payment_type`
- **Generated:** `SELECT 
  avg(CASE WHEN payment_type = 2 THEN total_amount ELSE NULL END) AS avg_cash_total,
  avg(CASE WHEN payment_type = 1 THEN total_amount ELSE NULL END) AS avg_credit_card_total
FROM taxi
WHERE EXTRACT(YEAR FROM tpep_pickup_datetime) = 2024`

### `multi-005` — What is the average speed in miles per hour?

- **Why:** wrong result: expected 1 row(s) ['avg_mph'], got 1 row(s) ['avg_speed_mph']
- **Expected:** `SELECT ROUND(AVG(trip_distance / (date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime) / 3600.0)), 2) AS avg_mph FROM taxi WHERE date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime) > 0 AND trip_distance > 0`
- **Generated:** `SELECT 
  ROUND(AVG(trip_distance / (date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime) * 1.0 / 60.0)) * 60.0, 2) AS avg_speed_mph
FROM taxi`


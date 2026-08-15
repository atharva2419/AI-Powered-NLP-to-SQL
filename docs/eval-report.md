# Evaluation report

_Generated 2026-08-15T02:13:03+00:00 · model `llama-3.1-8b-instant`_

Execution accuracy on a hand-written golden set: a generated query is
correct when its result set matches the reference query's result set.

| Metric | Value |
|--------|-------|
| Execution accuracy | **85%** |
| Valid SQL rate | 93% |
| Cases | 46 |
| Recovered by self-correction | 0 |
| Exhausted all retries | 3 |
| Median latency | 12017 ms |
| p95 latency | 31279 ms |

## By category

| Category | Accuracy | Cases |
|----------|----------|-------|
| aggregation | 100% | 7 |
| counting | 100% | 4 |
| filtering | 100% | 4 |
| grouping | 75% | 4 |
| multi_step | 20% | 5 |
| ranking | 100% | 3 |
| ratio | 33% | 3 |
| time_series | 100% | 6 |
| zones | 100% | 10 |

## By difficulty

| Difficulty | Accuracy | Cases |
|------------|----------|-------|
| easy | 100% | 16 |
| medium | 89% | 19 |
| hard | 55% | 11 |

## Failures (7)

### `group-003` — What is the average total amount by passenger count?

- **Why:** wrong result: expected 11 row(s), got 11 row(s)
- **Expected:** `SELECT passenger_count, ROUND(AVG(total_amount), 2) AS avg_total FROM taxi GROUP BY passenger_count ORDER BY passenger_count`
- **Generated:** `SELECT ROUND(AVG(total_amount), 2) AS avg_total_amount FROM taxi GROUP BY passenger_count`

### `ratio-001` — What percentage of trips are paid by credit card?

- **Why:** wrong result: expected 1 row(s), got 1 row(s)
- **Expected:** `SELECT ROUND(100.0 * SUM(CASE WHEN payment_type = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_credit_card FROM taxi`
- **Generated:** `SELECT ROUND(100.0 * COUNT(*) / COUNT(DISTINCT trip_id), 2) AS pct_credit_card FROM (SELECT VendorID, tpep_pickup_datetime, tpep_dropoff_datetime, passenger_count, trip_distance, RatecodeID, store_and_fwd_flag, PULocationID, DOLocationID, payment_type, fare_amount, extra, mta_tax, tip_amount, tolls_amount, improvement_surcharge, total_amount, congestion_surcharge, Airport_fee, pickup_borough, pickup_zone, dropoff_borough, dropoff_zone, ROW_NUMBER() OVER (PARTITION BY VendorID, tpep_pickup_datetime, tpep_dropoff_datetime, passenger_count, trip_distance, RatecodeID, store_and_fwd_flag, PULocationID, DOLocationID, fare_amount, extra, mta_tax, tip_amount, tolls_amount, improvement_surcharge, total_amount, congestion_surcharge, Airport_fee, pickup_borough, pickup_zone, dropoff_borough, dropoff_zone ORDER BY payment_type) AS trip_id FROM taxi) AS subquery WHERE payment_type = 1`

### `ratio-002` — What is the average tip as a percentage of the fare?

- **Why:** wrong result: expected 1 row(s), got 1 row(s)
- **Expected:** `SELECT ROUND(100.0 * SUM(tip_amount) / SUM(fare_amount), 2) AS tip_pct FROM taxi WHERE fare_amount > 0`
- **Generated:** `SELECT ROUND(100.0 * AVG(tip_amount) / AVG(fare_amount), 2) AS tip_pct FROM taxi`

### `multi-001` — For credit card trips, what is the average tip by passenger count?

- **Why:** execution error: Binder Error: column "passenger_count" must appear in the GROUP BY clause or must be part of an aggregate function.
Either add it to the GROUP BY list, or use "ANY_VALUE(passenger_count)" if the exact value of "passenger_count" is not important.

LINE 1: ...(AVG(CASE WHEN payment_type = 1 THEN tip_amount ELSE 0 END) / passenger_count, 2) AS avg_tip_per_passenger FROM taxi WHERE...
                                                                         ^
- **Expected:** `SELECT passenger_count, ROUND(AVG(tip_amount), 2) AS avg_tip FROM taxi WHERE payment_type = 1 GROUP BY passenger_count ORDER BY passenger_count`
- **Generated:** `SELECT ROUND(AVG(CASE WHEN payment_type = 1 THEN tip_amount ELSE 0 END) / passenger_count, 2) AS avg_tip_per_passenger FROM taxi WHERE payment_type = 1`

### `multi-002` — What is the average fare per mile?

- **Why:** wrong result: expected 1 row(s), got 1 row(s)
- **Expected:** `SELECT ROUND(SUM(fare_amount) / SUM(trip_distance), 2) AS fare_per_mile FROM taxi WHERE trip_distance > 0`
- **Generated:** `SELECT ROUND(AVG(fare_amount / trip_distance), 2) AS avg_fare_per_mile FROM taxi`

### `multi-003` — How many trips per hour on average during each month?

- **Why:** execution error: Binder Error: aggregate function calls cannot be nested

LINE 1: ..., EXTRACT(HOUR FROM tpep_pickup_datetime) AS hour, ROUND(AVG(COUNT(*)) / 24, 2) AS avg_trips_per_hour FROM taxi GROUP...
                                                                        ^
- **Expected:** `SELECT MONTH(tpep_pickup_datetime) AS month, ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT date_trunc('hour', tpep_pickup_datetime)), 2) AS avg_trips_per_hour FROM taxi GROUP BY month ORDER BY month`
- **Generated:** `SELECT EXTRACT(MONTH FROM tpep_pickup_datetime) AS month, EXTRACT(HOUR FROM tpep_pickup_datetime) AS hour, ROUND(AVG(COUNT(*)) / 24, 2) AS avg_trips_per_hour FROM taxi GROUP BY EXTRACT(MONTH FROM tpep_pickup_datetime), EXTRACT(HOUR FROM tpep_pickup_datetime)`

### `multi-005` — What is the average speed in miles per hour?

- **Why:** execution error: Binder Error: column "tpep_pickup_datetime" must appear in the GROUP BY clause or must be part of an aggregate function.
Either add it to the GROUP BY list, or use "ANY_VALUE(tpep_pickup_datetime)" if the exact value of "tpep_pickup_datetime" is not important.

LINE 1: ...* FROM (SELECT ROUND(AVG(trip_distance) / (date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime) / 60.0), 2...
                                                                          ^
- **Expected:** `SELECT ROUND(AVG(trip_distance / (date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime) / 3600.0)), 2) AS avg_mph FROM taxi WHERE date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime) > 0 AND trip_distance > 0`
- **Generated:** `SELECT ROUND(AVG(trip_distance) / (date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime) / 60.0), 2) AS avg_speed FROM taxi`


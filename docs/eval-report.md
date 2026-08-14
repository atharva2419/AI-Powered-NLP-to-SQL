# Evaluation report

_Generated 2026-08-14T01:12:34+00:00 · model `llama-3.1-8b-instant`_

Execution accuracy on a hand-written golden set: a generated query is
correct when its result set matches the reference query's result set.

| Metric | Value |
|--------|-------|
| Execution accuracy | **83%** |
| Valid SQL rate | 93% |
| Cases | 42 |
| Recovered by self-correction | 0 |
| Exhausted all retries | 3 |
| Median latency | 10106 ms |
| p95 latency | 12241 ms |

## By category

| Category | Accuracy | Cases |
|----------|----------|-------|
| aggregation | 86% | 7 |
| counting | 100% | 4 |
| filtering | 100% | 4 |
| grouping | 100% | 4 |
| multi_step | 20% | 5 |
| ranking | 100% | 3 |
| ratio | 33% | 3 |
| time_series | 100% | 6 |
| zones | 100% | 6 |

## By difficulty

| Difficulty | Accuracy | Cases |
|------------|----------|-------|
| easy | 100% | 16 |
| medium | 87% | 15 |
| hard | 55% | 11 |

## Failures (7)

### `agg-004` — What is the median fare amount?

- **Why:** execution error: Catalog Error: Aggregate Function with name percentile_cont does not exist!
Did you mean "pi"?

LINE 1: SELECT * FROM (SELECT ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fare_amount...
                                    ^
- **Expected:** `SELECT MEDIAN(fare_amount) AS median_fare FROM taxi`
- **Generated:** `SELECT ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY fare_amount) OVER (), 2) AS median_fare FROM taxi`

### `ratio-001` — What percentage of trips are paid by credit card?

- **Why:** wrong result: expected 1 row(s), got 1 row(s)
- **Expected:** `SELECT ROUND(100.0 * SUM(CASE WHEN payment_type = 1 THEN 1 ELSE 0 END) / COUNT(*), 2) AS pct_credit_card FROM taxi`
- **Generated:** `SELECT ROUND(100.0 * COUNT(*) / COUNT(DISTINCT trip_distance), 2) AS pct_credit_card FROM taxi WHERE payment_type = 1`

### `ratio-002` — What is the average tip as a percentage of the fare?

- **Why:** wrong result: expected 1 row(s), got 1 row(s)
- **Expected:** `SELECT ROUND(100.0 * SUM(tip_amount) / SUM(fare_amount), 2) AS tip_pct FROM taxi WHERE fare_amount > 0`
- **Generated:** `SELECT ROUND(100.0 * AVG(tip_amount) / AVG(fare_amount), 2) AS tip_pct FROM taxi`

### `multi-001` — For credit card trips, what is the average tip by passenger count?

- **Why:** wrong result: expected 10 row(s), got 10 row(s)
- **Expected:** `SELECT passenger_count, ROUND(AVG(tip_amount), 2) AS avg_tip FROM taxi WHERE payment_type = 1 GROUP BY passenger_count ORDER BY passenger_count`
- **Generated:** `SELECT ROUND(AVG(tip_amount) / passenger_count, 2) AS avg_tip_per_passenger FROM taxi WHERE payment_type = 1 GROUP BY passenger_count`

### `multi-002` — What is the average fare per mile?

- **Why:** wrong result: expected 1 row(s), got 1 row(s)
- **Expected:** `SELECT ROUND(SUM(fare_amount) / SUM(trip_distance), 2) AS fare_per_mile FROM taxi WHERE trip_distance > 0`
- **Generated:** `SELECT ROUND(AVG(fare_amount / trip_distance), 2) AS avg_fare_per_mile FROM taxi WHERE trip_distance > 0`

### `multi-003` — How many trips per hour on average during each month?

- **Why:** execution error: Binder Error: Referenced column "tpep_pickup_datetime" not found in FROM clause!
Candidate bindings: "trips"

LINE 1: SELECT * FROM (SELECT EXTRACT(MONTH FROM tpep_pickup_datetime) AS month, EXTRACT(HOUR FROM tpep_pick...
                                                 ^
- **Expected:** `SELECT MONTH(tpep_pickup_datetime) AS month, ROUND(COUNT(*) * 1.0 / COUNT(DISTINCT date_trunc('hour', tpep_pickup_datetime)), 2) AS avg_trips_per_hour FROM taxi GROUP BY month ORDER BY month`
- **Generated:** `SELECT EXTRACT(MONTH FROM tpep_pickup_datetime) AS month, EXTRACT(HOUR FROM tpep_pickup_datetime) AS hour, ROUND(AVG(trips) / 24, 2) AS avg_trips_per_hour FROM (SELECT EXTRACT(MONTH FROM tpep_pickup_datetime) AS month, EXTRACT(HOUR FROM tpep_pickup_datetime) AS hour, COUNT(*) AS trips FROM taxi GROUP BY EXTRACT(MONTH FROM tpep_pickup_datetime), EXTRACT(HOUR FROM tpep_pickup_datetime)) AS subquery GROUP BY month, hour`

### `multi-005` — What is the average speed in miles per hour?

- **Why:** execution error: Binder Error: column "tpep_pickup_datetime" must appear in the GROUP BY clause or must be part of an aggregate function.
Either add it to the GROUP BY list, or use "ANY_VALUE(tpep_pickup_datetime)" if the exact value of "tpep_pickup_datetime" is not important.

LINE 1: ...* FROM (SELECT ROUND(AVG(trip_distance) / (date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime) / 60.0), 2...
                                                                          ^
- **Expected:** `SELECT ROUND(AVG(trip_distance / (date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime) / 3600.0)), 2) AS avg_mph FROM taxi WHERE date_diff('second', tpep_pickup_datetime, tpep_dropoff_datetime) > 0 AND trip_distance > 0`
- **Generated:** `SELECT ROUND(AVG(trip_distance) / (date_diff('minute', tpep_pickup_datetime, tpep_dropoff_datetime) / 60.0), 2) AS avg_speed FROM taxi`


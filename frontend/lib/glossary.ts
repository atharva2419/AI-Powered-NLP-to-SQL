/**
 * Plain-English descriptions of the taxi table columns, based on the
 * official NYC TLC Yellow Taxi data dictionary. Keyed by column name as
 * returned by GET /api/schema.
 */
export const GLOSSARY: Record<string, string> = {
  VendorID:
    "Which company provided the trip record — 1 = Creative Mobile Technologies, 2 = Curb Mobility (formerly VeriFone), 6 = Myle, 7 = Helix.",
  tpep_pickup_datetime:
    "Date and time the meter was engaged (trip start). Ask about hours, days, or months.",
  tpep_dropoff_datetime:
    "Date and time the meter was disengaged (trip end). Combine with pickup time for trip duration.",
  passenger_count:
    "Number of passengers in the vehicle, entered by the driver.",
  trip_distance:
    "Trip distance in miles, as reported by the taximeter.",
  RatecodeID:
    "Rate type — 1 = standard, 2 = JFK, 3 = Newark, 4 = Nassau/Westchester, 5 = negotiated, 6 = group ride, 99 = unknown (467k trips use it).",
  store_and_fwd_flag:
    "Y if the record was held in vehicle memory before sending (no server connection), otherwise N.",
  PULocationID:
    "TLC taxi zone where the meter was engaged (pickup zone).",
  DOLocationID:
    "TLC taxi zone where the meter was disengaged (dropoff zone).",
  payment_type:
    "How the trip was paid — 1 = credit card, 2 = cash, 3 = no charge, 4 = dispute, 5 = unknown, 6 = voided. 0 is undocumented but covers 10% of 2024 (4.1M trips, averaging 18 miles vs ~3.5 elsewhere) — treat those separately.",
  fare_amount:
    "Meter fare based on time and distance, in dollars.",
  extra:
    "Rush-hour and overnight surcharges ($0.50–$1.00).",
  mta_tax:
    "Flat $0.50 MTA tax triggered by the metered rate.",
  tip_amount:
    "Tip in dollars — credit card tips only; cash tips are not recorded.",
  tolls_amount:
    "Total bridge and tunnel tolls paid during the trip.",
  improvement_surcharge:
    "Flat $0.30 improvement surcharge added at flag drop.",
  total_amount:
    "Total charged to the passenger, excluding cash tips.",
  congestion_surcharge:
    "$2.50 congestion fee for trips through Manhattan below 96th St.",
  Airport_fee:
    "$1.25 fee for pickups at JFK or LaGuardia airports.",
};

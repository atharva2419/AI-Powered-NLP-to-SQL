import { GLOSSARY } from '@/lib/glossary'

// Must stay in sync with what GET /api/schema returns: the 19 raw NYC TLC
// Yellow Taxi columns (see backend/data/fixture.py) plus the 4 zone columns
// the backend joins in from the TLC zone lookup (see query_engine.taxi_view_sql).
const TAXI_COLUMNS = [
  'VendorID',
  'tpep_pickup_datetime',
  'tpep_dropoff_datetime',
  'passenger_count',
  'trip_distance',
  'RatecodeID',
  'store_and_fwd_flag',
  'PULocationID',
  'DOLocationID',
  'payment_type',
  'fare_amount',
  'extra',
  'mta_tax',
  'tip_amount',
  'tolls_amount',
  'improvement_surcharge',
  'total_amount',
  'congestion_surcharge',
  'Airport_fee',
  // Denormalised from the TLC zone lookup so the model never writes a join.
  'pickup_borough',
  'pickup_zone',
  'dropoff_borough',
  'dropoff_zone',
]

describe('GLOSSARY', () => {
  it('covers every taxi column', () => {
    for (const col of TAXI_COLUMNS) {
      expect(GLOSSARY[col]).toBeDefined()
    }
  })

  it('has no entries for columns that do not exist', () => {
    for (const key of Object.keys(GLOSSARY)) {
      expect(TAXI_COLUMNS).toContain(key)
    }
  })

  it('every description is a non-empty sentence', () => {
    for (const desc of Object.values(GLOSSARY)) {
      expect(desc.length).toBeGreaterThan(10)
      expect(desc.endsWith('.')).toBe(true)
    }
  })

  it('explains the payment_type codes', () => {
    expect(GLOSSARY.payment_type).toMatch(/credit card/)
    expect(GLOSSARY.payment_type).toMatch(/cash/)
  })

  it('points people from the opaque location IDs to the named zone columns', () => {
    expect(GLOSSARY.PULocationID).toMatch(/pickup_zone/)
    expect(GLOSSARY.DOLocationID).toMatch(/dropoff_zone/)
  })

  it('names the boroughs so people know what values to ask for', () => {
    expect(GLOSSARY.pickup_borough).toMatch(/Manhattan/)
    expect(GLOSSARY.pickup_borough).toMatch(/Queens/)
  })
})

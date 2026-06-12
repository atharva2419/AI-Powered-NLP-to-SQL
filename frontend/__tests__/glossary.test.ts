import { GLOSSARY } from '@/lib/glossary'

// Must stay in sync with the 19 columns of the NYC TLC Yellow Taxi schema
// (see backend/tests/conftest.py for the canonical column list).
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
})

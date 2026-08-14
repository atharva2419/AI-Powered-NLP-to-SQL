import { decodeValue, formatColumnName, formatValue, isCodedColumn } from '@/lib/format'

describe('decoding coded columns', () => {
  it('decodes payment_type', () => {
    expect(formatValue('payment_type', 1)).toBe('Credit card')
    expect(formatValue('payment_type', 2)).toBe('Cash')
  })

  it('decodes the undocumented payment_type 0 rather than showing a bare zero', () => {
    // 4.09M trips in 2024 — the case that started all this.
    expect(formatValue('payment_type', 0)).toBe('Not provided')
  })

  it('decodes VendorID including the vendors added after the docs were written', () => {
    expect(formatValue('VendorID', 2)).toBe('Curb Mobility')
    expect(formatValue('VendorID', 6)).toBe('Myle')
    expect(formatValue('VendorID', 7)).toBe('Helix')
  })

  it('decodes RatecodeID 99', () => {
    expect(formatValue('RatecodeID', 99)).toBe('Unknown (99)')
  })

  it('decodes store_and_fwd_flag', () => {
    expect(formatValue('store_and_fwd_flag', 'Y')).toBe('Store and forward')
  })

  it('leaves unknown codes as-is rather than guessing', () => {
    expect(formatValue('payment_type', 42)).toBe('42')
  })

  it('does not decode columns it does not know', () => {
    expect(decodeValue('trip_distance', 1)).toBeNull()
    expect(formatValue('trip_distance', 1)).toBe('1')
  })

  it('reports which columns are coded', () => {
    expect(isCodedColumn('payment_type')).toBe(true)
    expect(isCodedColumn('fare_amount')).toBe(false)
  })
})

describe('number formatting', () => {
  it('groups large integers', () => {
    expect(formatValue('trips', 30452126)).toBe('30,452,126')
  })

  it('formats money columns as currency', () => {
    expect(formatValue('fare_amount', 18.37)).toBe('$18.37')
    expect(formatValue('avg_total_amount', 27.5)).toBe('$27.50')
    expect(formatValue('revenue', 1234.5)).toBe('$1,234.50')
  })

  it('formats percentage columns with a percent sign', () => {
    expect(formatValue('pct_credit_card', 67.42)).toBe('67.42%')
    expect(formatValue('tip_share', 12.1)).toBe('12.1%')
  })

  it('does not treat distance as money', () => {
    expect(formatValue('avg_distance', 3.54)).toBe('3.54')
  })

  it('caps runaway decimals', () => {
    expect(formatValue('avg_distance', 3.5412345)).toBe('3.54')
  })
})

describe('calendar formatting', () => {
  it('names months', () => {
    expect(formatValue('month', 1)).toBe('Jan')
    expect(formatValue('month', 12)).toBe('Dec')
  })

  it('names days of week using DuckDB 0=Sunday', () => {
    expect(formatValue('day_of_week', 0)).toBe('Sunday')
    expect(formatValue('dayofweek', 6)).toBe('Saturday')
  })

  it('renders hours in 12-hour form', () => {
    expect(formatValue('hour', 0)).toBe('12am')
    expect(formatValue('hour', 9)).toBe('9am')
    expect(formatValue('hour', 12)).toBe('12pm')
    expect(formatValue('hour', 17)).toBe('5pm')
  })

  it('does not treat an out-of-range value as a calendar value', () => {
    // A column called "month" holding a count of 47 is a count, not a month.
    expect(formatValue('month', 47)).toBe('47')
    expect(formatValue('hour', 99)).toBe('99')
  })
})

describe('other values', () => {
  it('renders null explicitly', () => {
    expect(formatValue('RatecodeID', null)).toBe('null')
    expect(formatValue('anything', undefined)).toBe('null')
  })

  it('tidies ISO timestamps', () => {
    expect(formatValue('tpep_pickup_datetime', '2024-01-01T08:00:00')).toBe('2024-01-01 08:00:00')
  })

  it('passes plain strings through', () => {
    expect(formatValue('some_label', 'hello')).toBe('hello')
  })
})

describe('formatColumnName', () => {
  it('humanises snake_case', () => {
    expect(formatColumnName('avg_fare_amount')).toBe('Avg fare amount')
  })

  it('handles a single word', () => {
    expect(formatColumnName('trips')).toBe('Trips')
  })

  it('handles an empty string', () => {
    expect(formatColumnName('')).toBe('')
  })
})

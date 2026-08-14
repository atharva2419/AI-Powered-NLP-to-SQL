import { detectChart, formatStatValue } from '@/lib/chart'

// ---------------------------------------------------------------------------
// detectChart
// ---------------------------------------------------------------------------
describe('detectChart', () => {
  it('returns a stat card for a single numeric value', () => {
    const spec = detectChart(['count_star()'], [[3066766]])
    expect(spec).toEqual({
      type: 'stat',
      valueLabel: 'count_star()',
      data: [{ x: 'count_star()', y: 3066766 }],
    })
  })

  it('returns a bar chart for category + numeric columns', () => {
    const spec = detectChart(
      ['payment_type', 'avg_distance'],
      [[1, 3.2], [2, 2.8], [3, 4.1]]
    )
    expect(spec?.type).toBe('bar')
    expect(spec?.valueLabel).toBe('avg_distance')
    expect(spec?.categoryLabel).toBe('payment_type')
    // x values are decoded here, not in the component, so the axis, the
    // tooltip and the results table cannot disagree about what a code means.
    expect(spec?.data).toEqual([
      { x: 'Credit card', y: 3.2 },
      { x: 'Cash', y: 2.8 },
      { x: 'No charge', y: 4.1 },
    ])
  })

  it('leaves non-coded categories as plain text', () => {
    const spec = detectChart(
      ['pickup_zone', 'trips'],
      [['Midtown', 12], ['JFK', 9]]
    )
    expect(spec?.data).toEqual([
      { x: 'Midtown', y: 12 },
      { x: 'JFK', y: 9 },
    ])
  })

  it('returns a line chart when the category column looks time-like', () => {
    expect(detectChart(['hour', 'trips'], [[8, 100], [9, 200]])?.type).toBe('line')
    expect(detectChart(['pickup_date', 'trips'], [['2024-01-01', 5], ['2024-01-02', 7]])?.type).toBe('line')
    expect(detectChart(['day_of_week', 'trips'], [[1, 10], [2, 20]])?.type).toBe('line')
  })

  it('returns null when the value column is not numeric', () => {
    expect(detectChart(['a', 'b'], [['x', 'y'], ['p', 'q']])).toBeNull()
  })

  it('returns null for a single non-numeric value', () => {
    expect(detectChart(['name'], [['Alice']])).toBeNull()
  })

  it('returns null for more than two columns', () => {
    expect(detectChart(['a', 'b', 'c'], [[1, 2, 3], [4, 5, 6]])).toBeNull()
  })

  it('returns null for a single row with two columns', () => {
    expect(detectChart(['a', 'b'], [[1, 2]])).toBeNull()
  })

  it('returns null for more than 50 rows', () => {
    const rows = Array.from({ length: 51 }, (_, i) => [String(i), i])
    expect(detectChart(['a', 'b'], rows)).toBeNull()
  })
})

// ---------------------------------------------------------------------------
// formatStatValue
// ---------------------------------------------------------------------------
describe('formatStatValue', () => {
  // Asserting literals, not `toLocaleString()`. Comparing the implementation
  // against itself passed on every machine — including ones whose system
  // locale grouped this as "30,66,766".
  it('adds thousands separators to integers', () => {
    expect(formatStatValue(3066766)).toBe('3,066,766')
  })

  it('caps floats at two decimal places', () => {
    expect(formatStatValue(14.23456)).toBe('14.23')
  })

  it('picks up the unit when given a column name', () => {
    expect(formatStatValue(18.37, 'avg_fare_amount')).toBe('$18.37')
    expect(formatStatValue(67.4, 'pct_credit_card')).toBe('67.4%')
  })
})

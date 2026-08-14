/**
 * Turning raw database values into things a human can read.
 *
 * The taxi table stores most of its interesting dimensions as integer codes.
 * A result table full of `payment_type = 1` is technically correct and
 * practically useless — the reader has to go find a data dictionary to learn
 * that it means "credit card". So values are decoded at the presentation
 * layer, in one place, used by the table, the chart axis, the tooltip and the
 * stat card alike.
 *
 * Decoding is keyed on column name and applied only to columns known to be
 * coded. If the model aliases `payment_type` to something else, the value
 * renders raw rather than being guessed at — a wrong label is worse than no
 * label.
 */

/** Code → label maps, from the NYC TLC data dictionary plus what the data actually contains. */
export const CODE_LABELS: Record<string, Record<string, string>> = {
  payment_type: {
    // 0 is not in the TLC dictionary, but it is 10% of 2024 (4.09M trips) and
    // those rows also have null RatecodeID and null store_and_fwd_flag. They
    // appear to be a separate record feed, and their trip distances run ~5x
    // the fleet average, so they are worth flagging rather than hiding.
    '0': 'Not provided',
    '1': 'Credit card',
    '2': 'Cash',
    '3': 'No charge',
    '4': 'Dispute',
    '5': 'Unknown',
    '6': 'Voided trip',
  },
  VendorID: {
    '1': 'Creative Mobile',
    '2': 'Curb Mobility',
    '6': 'Myle',
    '7': 'Helix',
  },
  RatecodeID: {
    '1': 'Standard rate',
    '2': 'JFK',
    '3': 'Newark',
    '4': 'Nassau/Westchester',
    '5': 'Negotiated fare',
    '6': 'Group ride',
    '99': 'Unknown (99)',
  },
  store_and_fwd_flag: {
    Y: 'Store and forward',
    N: 'Sent live',
  },
};

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// DuckDB's DAYOFWEEK is 0 = Sunday.
const DAYS = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday'];

// Formatting is pinned to en-US rather than the viewer's locale. Left to
// `undefined`, toLocaleString groups by the *system* locale, so the same
// 30452126 renders as "30,452,126" on one machine and "3,04,52,126" on
// another. The data is US municipal data quoted in USD; the grouping should
// not depend on who is looking at it.
const LOCALE = 'en-US';

const MONEY_RE = /fare|amount|revenue|tip|toll|surcharge|price|cost|fee/i;
const PERCENT_RE = /pct|percent|share|rate$/i;
const MONTH_RE = /^(month|pickup_month|.*_month)$/i;
const HOUR_RE = /^(hour|pickup_hour|.*_hour)$/i;
const DAY_RE = /^(day_of_week|dayofweek|dow|weekday)$/i;

/** Does this column hold codes we can decode? Used to decide whether a legend is worth showing. */
export function isCodedColumn(column: string): boolean {
  return column in CODE_LABELS;
}

/** Decode a coded value, or return null if this column/value pair isn't coded. */
export function decodeValue(column: string, value: unknown): string | null {
  const map = CODE_LABELS[column];
  if (!map || value === null || value === undefined) return null;
  return map[String(value)] ?? null;
}

function formatNumber(column: string, value: number): string {
  if (PERCENT_RE.test(column)) {
    return `${value.toLocaleString(LOCALE, { maximumFractionDigits: 2 })}%`;
  }
  if (MONEY_RE.test(column)) {
    return value.toLocaleString(LOCALE, {
      style: 'currency',
      currency: 'USD',
      maximumFractionDigits: 2,
    });
  }
  if (Number.isInteger(value)) return value.toLocaleString(LOCALE);
  return value.toLocaleString(LOCALE, { maximumFractionDigits: 2 });
}

/**
 * Render a single cell for display.
 *
 * Order matters: coded columns decode first, so `payment_type = 1` never
 * reaches the number formatter and come out as "1".
 */
export function formatValue(column: string, value: unknown): string {
  if (value === null || value === undefined) return 'null';

  const decoded = decodeValue(column, value);
  if (decoded !== null) return decoded;

  if (typeof value === 'number' && Number.isFinite(value)) {
    // Calendar-ish integers only decode inside their valid range, so a column
    // called "month" holding a count of 47 is not rendered as a month name.
    if (MONTH_RE.test(column) && Number.isInteger(value) && value >= 1 && value <= 12) {
      return MONTHS[value - 1];
    }
    if (DAY_RE.test(column) && Number.isInteger(value) && value >= 0 && value <= 6) {
      return DAYS[value];
    }
    if (HOUR_RE.test(column) && Number.isInteger(value) && value >= 0 && value <= 23) {
      const suffix = value < 12 ? 'am' : 'pm';
      const hour12 = value % 12 === 0 ? 12 : value % 12;
      return `${hour12}${suffix}`;
    }
    return formatNumber(column, value);
  }

  // ISO timestamps come back as strings from the API.
  if (typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T/.test(value)) {
    return value.replace('T', ' ').replace(/\.\d+$/, '');
  }

  return String(value);
}

/** `avg_fare_amount` → `Avg fare amount`, for table headers. */
export function formatColumnName(column: string): string {
  const spaced = column.replace(/_/g, ' ').trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

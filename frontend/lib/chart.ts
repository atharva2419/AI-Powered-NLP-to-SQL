import { formatValue } from "./format";

export interface ChartSpec {
  type: "stat" | "bar" | "line";
  /** label of the value column (y-axis / stat label) */
  valueLabel: string;
  /** label of the category column (x-axis) — absent for stat */
  categoryLabel?: string;
  /** x is display-ready: coded columns are already decoded to their labels */
  data: { x: string; y: number }[];
}

const TIME_PATTERN = /hour|date|day|month|year|week|time/i;
const MAX_CHART_ROWS = 50;

function isNumeric(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/**
 * Decide whether a query result can be charted, and how.
 *
 * - single numeric value            → stat card
 * - category + numeric column pairs → bar chart (line if x looks time-like)
 * - anything else                   → null (table only)
 */
export function detectChart(columns: string[], rows: unknown[][]): ChartSpec | null {
  if (columns.length === 1 && rows.length === 1 && isNumeric(rows[0][0])) {
    return {
      type: "stat",
      valueLabel: columns[0],
      data: [{ x: columns[0], y: rows[0][0] }],
    };
  }

  if (
    columns.length === 2 &&
    rows.length >= 2 &&
    rows.length <= MAX_CHART_ROWS &&
    rows.every((r) => isNumeric(r[1]))
  ) {
    // Decode here rather than in the component so the axis, the tooltip and
    // the table all show the same label for the same value.
    const data = rows.map((r) => ({ x: formatValue(columns[0], r[0]), y: r[1] as number }));
    return {
      type: TIME_PATTERN.test(columns[0]) ? "line" : "bar",
      valueLabel: columns[1],
      categoryLabel: columns[0],
      data,
    };
  }

  return null;
}

export function formatStatValue(value: number, column?: string): string {
  // With a column name available the value can pick up its unit ($ or %);
  // without one it falls back to a plain grouped number.
  if (column) return formatValue(column, value);
  if (Number.isInteger(value)) return value.toLocaleString('en-US');
  return value.toLocaleString('en-US', { maximumFractionDigits: 2 });
}

'use client';

import {
  Bar,
  BarChart,
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { detectChart, formatStatValue } from '@/lib/chart';
import { formatColumnName, formatValue } from '@/lib/format';

const AXIS_STYLE = { fontSize: 11, fill: '#a1a1aa' };
const ACCENT = '#f59e0b'; // amber-500 — taxi yellow

/** 30452126 → "30.5M". Trip counts are in the millions and blow out the axis gutter. */
function compactTick(value: number): string {
  if (Math.abs(value) >= 1_000_000) return `${(value / 1_000_000).toFixed(1)}M`;
  if (Math.abs(value) >= 1_000) return `${(value / 1_000).toFixed(0)}k`;
  return String(value);
}

export default function ResultChart({
  columns,
  rows,
}: {
  columns: string[];
  rows: unknown[][];
}) {
  const spec = detectChart(columns, rows);
  if (!spec) return null;

  // Recharts labels the tooltip with the raw dataKey ("y") and the bare x
  // value, which reads as "0 / y : 18.33". Both get replaced with the column's
  // real name and a formatted value.
  const tooltipFormatter = (value: unknown): [string, string] => [
    typeof value === 'number' ? formatValue(spec.valueLabel, value) : String(value),
    formatColumnName(spec.valueLabel),
  ];
  const tooltipLabelFormatter = (label: unknown) =>
    spec.categoryLabel ? `${formatColumnName(spec.categoryLabel)}: ${label}` : String(label);

  if (spec.type === 'stat') {
    return (
      <div
        data-testid="stat-card"
        className="rounded-lg border border-zinc-200 bg-white px-6 py-5 shadow-sm"
      >
        <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
          {formatColumnName(spec.valueLabel)}
        </p>
        <p className="mt-1 text-4xl font-semibold tracking-tight text-zinc-900">
          {formatStatValue(spec.data[0].y, spec.valueLabel)}
        </p>
      </div>
    );
  }

  return (
    <div
      data-testid={`${spec.type}-chart`}
      className="rounded-lg border border-zinc-200 bg-white p-4 shadow-sm"
    >
      <p className="mb-3 text-xs font-semibold uppercase tracking-widest text-zinc-400">
        {formatColumnName(spec.valueLabel)} by {formatColumnName(spec.categoryLabel ?? '')}
      </p>
      <ResponsiveContainer width="100%" height={260}>
        {spec.type === 'bar' ? (
          <BarChart data={spec.data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" vertical={false} />
            <XAxis dataKey="x" tick={AXIS_STYLE} tickLine={false} axisLine={{ stroke: '#e4e4e7' }} />
            <YAxis
              tick={AXIS_STYLE}
              tickLine={false}
              axisLine={false}
              width={56}
              tickFormatter={compactTick}
            />
            <Tooltip
              cursor={{ fill: '#fafafa' }}
              contentStyle={{ fontSize: 12, borderRadius: 8 }}
              formatter={tooltipFormatter}
              labelFormatter={tooltipLabelFormatter}
            />
            <Bar dataKey="y" name={spec.valueLabel} fill={ACCENT} radius={[4, 4, 0, 0]} maxBarSize={48} />
          </BarChart>
        ) : (
          <LineChart data={spec.data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" vertical={false} />
            <XAxis dataKey="x" tick={AXIS_STYLE} tickLine={false} axisLine={{ stroke: '#e4e4e7' }} />
            <YAxis
              tick={AXIS_STYLE}
              tickLine={false}
              axisLine={false}
              width={56}
              tickFormatter={compactTick}
            />
            <Tooltip
              contentStyle={{ fontSize: 12, borderRadius: 8 }}
              formatter={tooltipFormatter}
              labelFormatter={tooltipLabelFormatter}
            />
            <Line
              type="monotone"
              dataKey="y"
              name={spec.valueLabel}
              stroke={ACCENT}
              strokeWidth={2}
              dot={{ r: 2, fill: ACCENT }}
            />
          </LineChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

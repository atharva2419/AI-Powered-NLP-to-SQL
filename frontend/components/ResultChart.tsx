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

const AXIS_STYLE = { fontSize: 11, fill: '#a1a1aa' };
const ACCENT = '#f59e0b'; // amber-500 — taxi yellow

export default function ResultChart({
  columns,
  rows,
}: {
  columns: string[];
  rows: unknown[][];
}) {
  const spec = detectChart(columns, rows);
  if (!spec) return null;

  if (spec.type === 'stat') {
    return (
      <div
        data-testid="stat-card"
        className="rounded-lg border border-zinc-200 bg-white px-6 py-5 shadow-sm"
      >
        <p className="text-xs font-semibold uppercase tracking-widest text-zinc-400">
          {spec.valueLabel}
        </p>
        <p className="mt-1 text-4xl font-semibold tracking-tight text-zinc-900">
          {formatStatValue(spec.data[0].y)}
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
        {spec.valueLabel} by {spec.categoryLabel}
      </p>
      <ResponsiveContainer width="100%" height={260}>
        {spec.type === 'bar' ? (
          <BarChart data={spec.data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" vertical={false} />
            <XAxis dataKey="x" tick={AXIS_STYLE} tickLine={false} axisLine={{ stroke: '#e4e4e7' }} />
            <YAxis tick={AXIS_STYLE} tickLine={false} axisLine={false} width={48} />
            <Tooltip cursor={{ fill: '#fafafa' }} contentStyle={{ fontSize: 12, borderRadius: 8 }} />
            <Bar dataKey="y" name={spec.valueLabel} fill={ACCENT} radius={[4, 4, 0, 0]} maxBarSize={48} />
          </BarChart>
        ) : (
          <LineChart data={spec.data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#f4f4f5" vertical={false} />
            <XAxis dataKey="x" tick={AXIS_STYLE} tickLine={false} axisLine={{ stroke: '#e4e4e7' }} />
            <YAxis tick={AXIS_STYLE} tickLine={false} axisLine={false} width={48} />
            <Tooltip contentStyle={{ fontSize: 12, borderRadius: 8 }} />
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

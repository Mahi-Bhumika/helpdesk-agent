import { TooltipProps } from "recharts";

/**
 * Recharts renders tooltips outside your normal component tree, so it needs its
 * own explicit dark/glass styling rather than inheriting from globals.css.
 */
export default function ChartTooltip({ active, payload, label }: TooltipProps<number, string>) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="rounded-lg border border-white/[0.1] bg-obsidian-surface/95 backdrop-blur-glass px-3 py-2 shadow-card">
      <p className="text-xs text-text-secondary mb-1">{label}</p>
      {payload.map((entry) => (
        <p key={entry.dataKey as string} className="text-sm font-medium text-text-primary">
          {entry.value} {entry.name}
        </p>
      ))}
    </div>
  );
}

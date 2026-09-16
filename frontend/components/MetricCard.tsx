import { ReactNode } from "react";
import GlassCard from "./GlassCard";
import clsx from "clsx";

interface MetricCardProps {
  label: string;
  value: string | number;
  /** Optional small icon, e.g. from lucide-react — rendered top-right, muted */
  icon?: ReactNode;
  /** Optional trend, e.g. { value: "+12%", direction: "up" } — omit if not meaningful for this metric */
  trend?: {
    value: string;
    direction: "up" | "down" | "flat";
  };
  /** Shows a pulsing skeleton instead of the value, for first-load / cold-start states */
  loading?: boolean;
}

const trendColor: Record<string, string> = {
  up: "text-status-active",
  down: "text-status-declined",
  flat: "text-text-muted",
};

export default function MetricCard({ label, value, icon, trend, loading }: MetricCardProps) {
  return (
    <GlassCard padding="lg" className="flex flex-col gap-2">
      <div className="flex items-start justify-between">
        <span className="text-sm text-text-secondary">{label}</span>
        {icon && <span className="text-text-muted">{icon}</span>}
      </div>

      {loading ? (
        <div className="h-9 w-24 rounded-md bg-white/[0.06] animate-pulse" />
      ) : (
        <div className="flex items-baseline gap-2">
          <span className="text-3xl font-semibold tracking-tight text-text-primary">
            {value}
          </span>
          {trend && (
            <span className={clsx("text-xs font-medium", trendColor[trend.direction])}>
              {trend.value}
            </span>
          )}
        </div>
      )}
    </GlassCard>
  );
}

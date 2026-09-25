"use client";

import { useEffect, useState } from "react";
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { SupabaseClient } from "@supabase/supabase-js";
import GlassCard from "./GlassCard";
import ChartTooltip from "./ChartTooltip";
import { fetchSessionsPerDay, DailyCount } from "@/lib/analyticsQueries";

interface SessionsOverTimeChartProps {
  supabase: SupabaseClient;
  daysBack?: number;
}

export default function SessionsOverTimeChart({
  supabase,
  daysBack = 14,
}: SessionsOverTimeChartProps) {
  const [data, setData] = useState<DailyCount[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetchSessionsPerDay(supabase, daysBack)
      .then((rows) => {
        if (!cancelled) setData(rows);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message ?? "Couldn't load sessions data.");
      });

    return () => {
      cancelled = true;
    };
  }, [supabase, daysBack]);

  const isEmpty = data && data.every((d) => d.count === 0);

  return (
    <GlassCard padding="lg">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-medium text-text-secondary">
          Chat sessions — last {daysBack} days
        </h3>
      </div>

      {error && <p className="text-sm text-status-declined">{error}</p>}

      {!error && !data && (
        <div className="h-56 w-full rounded-md bg-white/[0.04] animate-pulse" />
      )}

      {!error && data && isEmpty && (
        <div className="h-56 flex flex-col items-center justify-center text-center gap-1">
          <p className="text-sm text-text-secondary">No sessions yet in this window.</p>
          <p className="text-xs text-text-muted">
            Once your widget starts getting real conversations, they&apos;ll show up here.
          </p>
        </div>
      )}

      {!error && data && !isEmpty && (
        <ResponsiveContainer width="100%" height={224}>
          <AreaChart data={data} margin={{ top: 4, right: 4, left: -20, bottom: 0 }}>
            <defs>
              <linearGradient id="sessionsGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#7C3AED" stopOpacity={0.35} />
                <stop offset="100%" stopColor="#7C3AED" stopOpacity={0} />
              </linearGradient>
            </defs>
            <CartesianGrid stroke="rgba(255,255,255,0.06)" vertical={false} />
            <XAxis
              dataKey="date"
              stroke="#6B6B72"
              fontSize={12}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              stroke="#6B6B72"
              fontSize={12}
              tickLine={false}
              axisLine={false}
              allowDecimals={false}
              width={28}
            />
            <Tooltip content={<ChartTooltip />} />
            <Area
              type="monotone"
              dataKey="count"
              name="sessions"
              stroke="#7C3AED"
              strokeWidth={2}
              fill="url(#sessionsGradient)"
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </GlassCard>
  );
}

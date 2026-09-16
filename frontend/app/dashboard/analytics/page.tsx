"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";
import MetricCard from "@/components/MetricCard";
import SessionsOverTimeChart from "@/components/SessionsOverTimeChart";
import MessagesVolumeChart from "@/components/MessagesVolumeChart";

type Stats = {
    sessionCount: number;
    messageCount: number;
    avgLatencyMs: number | null;
};

export default function AnalyticsPage() {
    const { tenantId } = useAuth();
    const [stats, setStats] = useState<Stats | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchStats() {
            if (!tenantId) return;
            setLoading(true);

            const [sessionRes, messageRes, latencyRes] = await Promise.all([
                supabase
                    .from("chat_sessions")
                    .select("*", { count: "exact", head: true })
                    .eq("tenant_id", tenantId),
                supabase
                    .from("messages")
                    .select("*", { count: "exact", head: true })
                    .eq("tenant_id", tenantId),
                supabase
                    .from("messages")
                    .select("response_latency_ms")
                    .eq("tenant_id", tenantId)
                    .eq("sender", "bot")
                    .not("response_latency_ms", "is", null),
            ]);

            const latencies = (latencyRes.data ?? []).map((r) => r.response_latency_ms as number);
            const avgLatencyMs =
                latencies.length > 0
                    ? Math.round(latencies.reduce((sum, v) => sum + v, 0) / latencies.length)
                    : null;

            setStats({
                sessionCount: sessionRes.count ?? 0,
                messageCount: messageRes.count ?? 0,
                avgLatencyMs,
            });
            setLoading(false);
        }
        fetchStats();
    }, [tenantId]);

    if (loading) return <p className="text-sm text-text-secondary">Loading analytics...</p>;
    if (!stats) return <p className="text-sm text-status-declined">Couldn't load analytics.</p>;

    return (
        <div className="p-8">
            <h1 className="text-2xl font-semibold text-text-primary mb-6">Analytics</h1>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <MetricCard label="Chat sessions" value={stats.sessionCount} />
                <MetricCard label="Total messages" value={stats.messageCount} />
                <MetricCard
                    label="Avg. response time"
                    value={stats.avgLatencyMs != null ? `${stats.avgLatencyMs}ms` : "—"}
                />
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mt-6">
                <SessionsOverTimeChart supabase={supabase} daysBack={14} />
                <MessagesVolumeChart supabase={supabase} daysBack={14} />
            </div>
        </div>
    );
}
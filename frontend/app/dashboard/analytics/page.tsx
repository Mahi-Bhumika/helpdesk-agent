"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";

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

    if (loading) return <p className="text-sm text-gray-400">Loading analytics...</p>;
    if (!stats) return <p className="text-sm text-red-500">Couldn't load analytics.</p>;

    return (
        <div>
            <h1 className="text-xl font-bold mb-6">Analytics</h1>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
                <StatCard label="Chat sessions" value={stats.sessionCount} />
                <StatCard label="Total messages" value={stats.messageCount} />
                <StatCard
                    label="Avg. response time"
                    value={stats.avgLatencyMs != null ? `${stats.avgLatencyMs}ms` : "—"}
                />
            </div>
        </div>
    );
}

function StatCard({ label, value }: { label: string; value: string | number }) {
    return (
        <div className="border border-gray-800 rounded-lg p-4">
            <p className="text-sm text-gray-400">{label}</p>
            <p className="text-2xl font-bold mt-1">{value}</p>
        </div>
    );
}
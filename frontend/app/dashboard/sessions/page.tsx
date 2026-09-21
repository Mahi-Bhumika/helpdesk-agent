"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authedFetch } from "@/lib/api";
import GlassCard from "@/components/GlassCard";
import PillBadge from "@/components/PillBadge";

type SessionSummary = {
    session_id: string;
    end_user_name: string | null;
    end_user_email: string | null;
    start_datetime: string;
    end_datetime: string | null;
    customer_satisfaction: number | null;
     message_count: number | null;
};

export default function SessionsListPage() {
    const router = useRouter();
    const [sessions, setSessions] = useState<SessionSummary[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    const [startDate, setStartDate] = useState("");
    const [endDate, setEndDate] = useState("");
    const [csatFilter, setCsatFilter] = useState("");

    useEffect(() => {
        async function fetchSessions() {
            setLoading(true);
            setError(null);
            try {
                const params = new URLSearchParams();
                if (startDate) params.set("start_date", startDate);
                if (endDate) params.set("end_date", endDate);
                if (csatFilter) params.set("min_csat", csatFilter);

                const query = params.toString() ? `?${params.toString()}` : "";
                const res = await authedFetch(`/sessions${query}`, { method: "GET" });
                if (!res.ok) throw new Error(`Failed to load sessions (HTTP ${res.status})`);
                setSessions(await res.json());
            } catch (err) {
                setError(err instanceof Error ? err.message : "Something went wrong.");
            } finally {
                setLoading(false);
            }
        }
        fetchSessions();
    }, [startDate, endDate, csatFilter]);

    function formatDate(iso: string) {
        return new Date(iso).toLocaleString(undefined, {
            month: "short",
            day: "numeric",
            hour: "numeric",
            minute: "2-digit",
        });
    }

    return (
        <div className="p-8">
            <h1 className="text-2xl font-semibold text-text-primary mb-6">Chat Sessions</h1>

            <div className="flex flex-wrap items-end gap-4 mb-6">
                <label className="flex flex-col gap-1.5">
                    <span className="text-xs text-text-secondary">From</span>
                    <input
                        type="date"
                        value={startDate}
                        onChange={(e) => setStartDate(e.target.value)}
                        className="rounded-lg border border-white/[0.1] bg-white/[0.05] px-3 py-2 text-sm text-text-primary"
                    />
                </label>
                <label className="flex flex-col gap-1.5">
                    <span className="text-xs text-text-secondary">To</span>
                    <input
                        type="date"
                        value={endDate}
                        onChange={(e) => setEndDate(e.target.value)}
                        className="rounded-lg border border-white/[0.1] bg-white/[0.05] px-3 py-2 text-sm text-text-primary"
                    />
                </label>
                <label className="flex flex-col gap-1.5">
                    <span className="text-xs text-text-secondary">Min CSAT</span>
                    <select
                        value={csatFilter}
                        onChange={(e) => setCsatFilter(e.target.value)}
                        className="rounded-lg border border-white/[0.1] bg-white/[0.05] px-3 py-2 text-sm text-text-primary [&>option]:bg-white [&>option]:text-gray-900"
                    >
                    <option value="">Any</option>
                    <option value="1">1+</option>
                    <option value="2">2+</option>
                    <option value="3">3+</option>
                    <option value="4">4+</option>
                    <option value="5">5</option>
                </select>
                </label>
            </div>

            <GlassCard padding="lg">
                {loading && (
                    <div className="space-y-3">
                        {[...Array(5)].map((_, i) => (
                            <div key={i} className="h-10 w-full rounded-lg bg-white/[0.04] animate-pulse" />
                        ))}
                    </div>
                )}

                {!loading && error && (
                    <p className="text-sm text-status-declined">{error}</p>
                )}

                {!loading && !error && sessions.length === 0 && (
                    <p className="text-sm text-text-secondary">No sessions yet.</p>
                )}

                {!loading && !error && sessions.length > 0 && (
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left text-text-muted text-xs border-b border-white/[0.08]">
                                <th className="pb-2 font-medium">Visitor</th>
                                <th className="pb-2 font-medium">Started</th>
                                <th className="pb-2 font-medium">Messages</th> 
                                <th className="pb-2 font-medium">Status</th>
                                <th className="pb-2 font-medium">CSAT</th>
                            </tr>
                        </thead>
                        <tbody>
                            {sessions.map((s, i) => (
                                <tr
                                    key={s.session_id}
                                    onClick={() => router.push(`/dashboard/sessions/${s.session_id}`)}
                                    className={`cursor-pointer hover:bg-white/[0.06] transition-colors ${
                                        i % 2 === 0 ? "bg-white/[0.02]" : ""
                                    }`}
                                >
                                    <td className="py-3 text-text-primary">
                                        {s.end_user_name || s.end_user_email || "Anonymous visitor"}
                                    </td>
                                    <td className="py-3 text-text-secondary">{formatDate(s.start_datetime)}</td>
                                    <td className="py-3 text-text-secondary">{s.message_count ?? "—"}</td>
                                    <td className="py-3">
                                        {s.end_datetime ? (
                                            <PillBadge status="completed" />
                                        ) : (
                                            <PillBadge status="active" label="Ongoing" />
                                        )}
                                    </td>
                                    <td className="py-3 text-text-secondary">
                                        {s.customer_satisfaction != null ? `${s.customer_satisfaction}/5` : "—"}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </GlassCard>
        </div>
    );
}
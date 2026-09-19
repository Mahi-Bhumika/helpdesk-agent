"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { authedFetch } from "@/lib/api";
import GlassCard from "@/components/GlassCard";
import Button from "@/components/Button";

type MessageSource = {
    chunk_text: string;
    chunk_index: number;
    relevance_score: number;
};

type Message = {
    message_id: string;
    sender: "user" | "bot";
    content: string;
    response_latency_ms: number | null;
    created_at: string;
    sources: MessageSource[];
};

export default function SessionTranscriptPage() {
    const { sessionId } = useParams<{ sessionId: string }>();
    const router = useRouter();
    const [messages, setMessages] = useState<Message[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [forbidden, setForbidden] = useState(false);

    useEffect(() => {
        async function fetchTranscript() {
            setLoading(true);
            setError(null);
            setForbidden(false);
            try {
                const res = await authedFetch(`/sessions/${sessionId}/messages`, { method: "GET" });
                if (res.status === 403) { setForbidden(true); return; }
                if (!res.ok) throw new Error(`Failed to load transcript (HTTP ${res.status})`);
                setMessages(await res.json());
            } catch (err) {
                setError(err instanceof Error ? err.message : "Something went wrong.");
            } finally {
                setLoading(false);
            }
        }
        if (sessionId) fetchTranscript();
    }, [sessionId]);

    function exportCsv() {
        if (messages.length === 0) return;
        const rows = [
            ["Timestamp", "Sender", "Message", "Latency (ms)"],
            ...messages.map((m) => [
                m.created_at,
                m.sender,
                m.content.replace(/\n/g, " "),
                m.response_latency_ms?.toString() ?? "",
            ]),
        ];
        const csv = rows
            .map((r) => r.map((cell) => `"${cell.replace(/"/g, '""')}"`).join(","))
            .join("\n");
        const blob = new Blob([csv], { type: "text/csv" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `session-${sessionId}.csv`;
        a.click();
        URL.revokeObjectURL(url);
    }

    return (
        <div className="p-8">
            <div className="flex items-center justify-between mb-6">
                <button
                    onClick={() => router.push("/dashboard/sessions")}
                    className="text-sm text-accent-violet hover:underline"
                >
                    ← Back to sessions
                </button>
                {messages.length > 0 && (
                    <Button variant="secondary" size="sm" onClick={exportCsv}>
                        Export CSV
                    </Button>
                )}
            </div>

            <h1 className="text-2xl font-semibold text-text-primary mb-6">Session Transcript</h1>

            <GlassCard padding="lg">
                {loading && (
                    <div className="space-y-3">
                        {[...Array(4)].map((_, i) => (
                            <div key={i} className="h-12 w-2/3 rounded-2xl bg-white/[0.04] animate-pulse" />
                        ))}
                    </div>
                )}

                {!loading && forbidden && (
                    <p className="text-sm text-status-declined">
                        You don't have access to this session — it may belong to a different tenant.
                    </p>
                )}

                {!loading && !forbidden && error && (
                    <p className="text-sm text-status-declined">{error}</p>
                )}

                {!loading && !forbidden && !error && messages.length === 0 && (
                    <p className="text-sm text-text-secondary">No messages in this session.</p>
                )}

                {!loading && !forbidden && !error && messages.length > 0 && (
                    <div className="flex flex-col gap-3">
                        {messages.map((msg) => (
                            <div
                                key={msg.message_id}
                                className={
                                    msg.sender === "user"
                                        ? "self-start max-w-[80%] rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm bg-white/[0.06] text-text-primary"
                                        : "self-end max-w-[80%] rounded-2xl rounded-br-sm px-4 py-2.5 text-sm bg-gradient-brand-soft border border-white/[0.08] text-text-primary"
                                }
                            >
                                <p>{msg.content}</p>
                                {msg.sender === "bot" && msg.response_latency_ms != null && (
                                    <p className="text-xs text-text-muted mt-1">{msg.response_latency_ms}ms</p>
                                )}
                                {msg.sender === "bot" && msg.sources.length > 0 && (
                                    <details className="mt-2 text-xs text-text-muted">
                                        <summary className="cursor-pointer hover:text-text-secondary">
                                            {msg.sources.length} source{msg.sources.length > 1 ? "s" : ""} cited
                                        </summary>
                                        <ul className="mt-1.5 space-y-1.5">
                                            {msg.sources.map((src, i) => (
                                                <li key={i} className="border-l-2 border-white/[0.1] pl-2">
                                                    <span className="font-mono text-status-completed">
                                                        #{src.chunk_index} · {(src.relevance_score * 100).toFixed(0)}% match
                                                    </span>
                                                    <p className="italic text-text-secondary mt-0.5">{src.chunk_text}</p>
                                                </li>
                                            ))}
                                        </ul>
                                    </details>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </GlassCard>
        </div>
    );
}
"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { authedFetch } from "@/lib/api";
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

function escapeCSV(value: string): string {
    return `"${value.replace(/"/g, '""')}"`;
}

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

    function downloadCSV() {
        const header = ["Sender", "Message", "Latency (ms)", "Timestamp", "Sources"];
        const rows = messages.map((msg) => {
            const sources = msg.sources
                .map((s) => `#${s.chunk_index} (${(s.relevance_score * 100).toFixed(0)}%)`)
                .join("; ");
            return [
                msg.sender,
                msg.content,
                msg.response_latency_ms != null ? String(msg.response_latency_ms) : "",
                new Date(msg.created_at).toLocaleString(),
                sources,
            ];
        });

        const csv = [header, ...rows]
            .map((row) => row.map(escapeCSV).join(","))
            .join("\n");

        const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `session-${sessionId}-transcript.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
    }

    return (
        <div className="p-8">
            <div className="flex items-center justify-between mb-4">
                <button
                    onClick={() => router.push("/dashboard/sessions")}
                    className="text-sm text-violet-400 hover:text-violet-300 hover:underline"
                >
                    ← Back to sessions
                </button>
                <Button variant="secondary" onClick={downloadCSV} disabled={messages.length === 0}>
                    Export CSV
                </Button>
            </div>
            <h1 className="text-xl font-semibold text-text-primary mb-4">Session Transcript</h1>

            {loading ? (
                <p className="text-sm text-text-secondary">Loading transcript...</p>
            ) : forbidden ? (
                <p className="text-sm text-red-400">You don&apos;t have access to this session — it may belong to a different tenant.</p>
            ) : error ? (
                <p className="text-sm text-red-400">{error}</p>
            ) : messages.length === 0 ? (
                <p className="text-sm text-text-secondary">No messages in this session.</p>
            ) : (
                <div className="flex flex-col gap-3">
                    {messages.map((msg) => (
                        <div
                            key={msg.message_id}
                            className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm ${
                                msg.sender === "user"
                                    ? "self-end bg-gradient-to-br from-[#4F46E5] to-[#7C3AED] text-white rounded-br-sm"
                                    : "self-start bg-white/[0.08] text-text-primary border border-white/[0.08] rounded-bl-sm"
                            }`}
                        >
                            <p>{msg.content}</p>
                            {msg.sender === "bot" && msg.response_latency_ms != null && (
                                <p className="text-xs text-text-muted mt-1">{msg.response_latency_ms}ms</p>
                            )}
                            {msg.sender === "bot" && msg.sources.length > 0 && (
                                <details className="mt-2 text-xs text-text-secondary">
                                    <summary className="cursor-pointer text-text-muted">
                                        {msg.sources.length} source{msg.sources.length > 1 ? "s" : ""}
                                    </summary>
                                    <ul className="mt-1 space-y-1">
                                        {msg.sources.map((src, i) => (
                                            <li key={i} className="border-l-2 border-white/[0.15] pl-2">
                                                <span className="font-mono text-text-muted">#{src.chunk_index} · {(src.relevance_score * 100).toFixed(0)}% match</span>
                                                <p className="italic">{src.chunk_text}</p>
                                            </li>
                                        ))}
                                    </ul>
                                </details>
                            )}
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
}
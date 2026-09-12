"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { authedFetch } from "@/lib/api";

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

    return (
        <div>
            <button onClick={() => router.push("/dashboard/sessions")} className="text-sm text-blue-400 hover:underline mb-4">
                ← Back to sessions
            </button>
            <h1 className="text-xl font-bold mb-4">Session Transcript</h1>

            {loading ? (
                <p className="text-sm text-gray-400">Loading transcript...</p>
            ) : forbidden ? (
                <p className="text-sm text-red-500">You don't have access to this session — it may belong to a different tenant.</p>
            ) : error ? (
                <p className="text-sm text-red-500">{error}</p>
            ) : messages.length === 0 ? (
                <p className="text-sm text-gray-400">No messages in this session.</p>
            ) : (
                <div className="flex flex-col gap-3">
                    {messages.map((msg) => (
                        <div
                            key={msg.message_id}
                            className={`max-w-[80%] rounded-xl px-4 py-2 text-sm ${
                                msg.sender === "user" ? "self-end bg-blue-600 text-white" : "self-start bg-gray-800 text-gray-100"
                            }`}
                        >
                            <p>{msg.content}</p>
                            {msg.sender === "bot" && msg.response_latency_ms != null && (
                                <p className="text-xs text-gray-400 mt-1">{msg.response_latency_ms}ms</p>
                            )}
                            {msg.sender === "bot" && msg.sources.length > 0 && (
                                <details className="mt-2 text-xs text-gray-400">
                                    <summary className="cursor-pointer">
                                        {msg.sources.length} source{msg.sources.length > 1 ? "s" : ""}
                                    </summary>
                                    <ul className="mt-1 space-y-1">
                                        {msg.sources.map((src, i) => (
                                            <li key={i} className="border-l-2 border-gray-600 pl-2">
                                                <span className="font-mono">#{src.chunk_index} · {(src.relevance_score * 100).toFixed(0)}% match</span>
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
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { authedFetch } from "@/lib/api";

type SessionSummary = {
    session_id: string;
    start_datetime: string;
    end_datetime: string | null;
    customer_satisfaction: number | null;
    message_count: number;
};

export default function SessionsPage() {
    const [sessions, setSessions] = useState<SessionSummary[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
        async function fetchSessions() {
            setLoading(true);
            setError(null);
            try {
                const res = await authedFetch("/sessions", { method: "GET" });
                if (!res.ok) throw new Error(`Failed to load sessions (HTTP ${res.status})`);
                setSessions(await res.json());
            } catch (err) {
                setError(err instanceof Error ? err.message : "Something went wrong.");
            } finally {
                setLoading(false);
            }
        }
        fetchSessions();
    }, []);

    function formatRelativeTime(iso: string) {
        const diffMins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
        if (diffMins < 1) return "just now";
        if (diffMins < 60) return `${diffMins}m ago`;
        const diffHours = Math.round(diffMins / 60);
        if (diffHours < 24) return `${diffHours}h ago`;
        return `${Math.round(diffHours / 24)}d ago`;
    }

    return (
        <div>
            <h1 className="text-xl font-bold mb-4">Chat Sessions</h1>

            {loading ? (
                <p className="text-sm text-gray-400">Loading sessions...</p>
            ) : error ? (
                <p className="text-sm text-red-500">{error}</p>
            ) : sessions.length === 0 ? (
                <p className="text-sm text-gray-400">No chat sessions yet.</p>
            ) : (
                <table className="w-full text-left border-collapse">
                    <thead>
                        <tr className="border-b border-gray-700">
                            <th className="py-2 pr-4">Started</th>
                            <th className="py-2 pr-4">Messages</th>
                            <th className="py-2 pr-4">Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {sessions.map((session) => (
                            <tr key={session.session_id} className="border-b border-gray-800 hover:bg-gray-900">
                                <td className="py-2 pr-4">
                                    <Link href={`/dashboard/sessions/${session.session_id}`} className="block">
                                        {formatRelativeTime(session.start_datetime)}
                                    </Link>
                                </td>
                                <td className="py-2 pr-4">
                                    <Link href={`/dashboard/sessions/${session.session_id}`} className="block">
                                        {session.message_count}
                                    </Link>
                                </td>
                                <td className="py-2 pr-4">
                                    <Link href={`/dashboard/sessions/${session.session_id}`} className="block">
                                        {session.end_datetime ? "Ended" : "Ongoing"}
                                    </Link>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}
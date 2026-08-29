"use client"

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";

export default function AnalyticsPage() {
    const { tenantId } = useAuth();
    const [messageCount, setMessageCount] = useState<number | null>(null);
    const [sessionCount, setSessionCount] = useState<number | null>(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        async function fetchStats() {
            if (!tenantId) return;
            setLoading(true);

            const { count: msgCount } = await supabase
                .from("messages")
                .select("*", { count: "exact", head: true })
                .eq("tenant_id", tenantId);

            const { count: sessCount } = await supabase
                .from("chat_sessions")
                .select("*", { count: "exact", head: true })
                .eq("tenant_id", tenantId);

            setMessageCount(msgCount ?? 0);
            setSessionCount(sessCount ?? 0);
            setLoading(false);
        }
        fetchStats();
    }, [tenantId]);

    if (!tenantId || loading) {
        return <div>Loading analytics...</div>;
    }

    return (
        <div>
            <h1 className="text-xl font-bold mb-6">Analytics</h1>
            <div className="grid grid-cols-2 gap-4 max-w-md">
                <div className="border border-gray-700 rounded-md p-4">
                    <p className="text-sm text-gray-400">Total Sessions</p>
                    <p className="text-3xl font-bold">{sessionCount}</p>
                </div>
                <div className="border border-gray-700 rounded-md p-4">
                    <p className="text-sm text-gray-400">Total Messages</p>
                    <p className="text-3xl font-bold">{messageCount}</p>
                </div>
            </div>
        </div>
    );
}
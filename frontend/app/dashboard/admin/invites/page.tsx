"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/lib/auth-context";
import { authedFetch } from "@/lib/api";
import { useRouter } from "next/navigation";

type PendingUser = {
    user_id: string;
    email: string;
    invited_at: string | null;
    created_at: string;
};


export default function InvitesAdminPage() {
    
    const { role, loading : authLoading} = useAuth();
    const router = useRouter();

    useEffect(() => {
        if (!authLoading && role !== "owner") {
            router.push("/dashboard/member");
        }
    }, [authLoading, role, router]);


    const [pending, setPending] = useState<PendingUser[]>([]);
    const [loading, setLoading] = useState(true);
    const [actioningId, setActioningId] = useState<string | null>(null);
    const [error, setError] = useState<string | null>(null);

    const fetchPending = useCallback(async () => {
        setLoading(true);
        setError(null);
        try {
            const res = await authedFetch("/admin/pending-users", { method: "GET" });
            if (!res.ok) throw new Error(`Failed to load pending users (${res.status})`);
            const data = await res.json();
            setPending(data);
        } catch (e) {
            setError(e instanceof Error ? e.message : "Something went wrong");
        } finally {
            setLoading(false);
        }
    }, []);

    useEffect(() => {
        fetchPending();
    }, [fetchPending]);

    const handleDecision = async (userId: string, action: "approve" | "decline") => {
        setActioningId(userId);
        setError(null);
        try {
            const res = await authedFetch(`/admin/${action}-user`, {
                method: "POST",
                body: JSON.stringify({ user_id: userId }),
            });
            if (!res.ok) throw new Error(`Failed to ${action} user (${res.status})`);
            // Optimistic-ish: just refetch the real list rather than manually
            // splicing state, so it always reflects the DB, not a guess.
            await fetchPending();
        } catch (e) {
            setError(e instanceof Error ? e.message : "Something went wrong");
        } finally {
            setActioningId(null);
        }
    };

    if (loading) return <p className="text-sm text-gray-400">Loading pending requests...</p>;

    return (
        <div>
            <h1 className="text-xl font-bold mb-4">Pending Invites</h1>

            {error && <p className="mb-4 text-sm text-red-500">{error}</p>}

            {pending.length === 0 ? (
                <p className="text-sm text-gray-400">No pending requests.</p>
            ) : (
                <table className="w-full text-left border-collapse">
                    <thead>
                        <tr className="border-b border-gray-700">
                            <th className="py-2 pr-4">Email</th>
                            <th className="py-2 pr-4">Requested</th>
                            <th className="py-2 pr-4">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {pending.map((u) => (
                            <tr key={u.user_id} className="border-b border-gray-800">
                                <td className="py-2 pr-4">{u.email}</td>
                                <td className="py-2 pr-4">
                                    {u.invited_at ? new Date(u.invited_at).toLocaleString() : "—"}
                                </td>
                                <td className="py-2 pr-4 flex gap-2">
                                    <button
                                        disabled={actioningId === u.user_id}
                                        onClick={() => handleDecision(u.user_id, "approve")}
                                        className="rounded-md bg-green-700 px-3 py-1 text-sm text-white disabled:opacity-50"
                                    >
                                        Accept
                                    </button>
                                    <button
                                        disabled={actioningId === u.user_id}
                                        onClick={() => handleDecision(u.user_id, "decline")}
                                        className="rounded-md bg-red-700 px-3 py-1 text-sm text-white disabled:opacity-50"
                                    >
                                        Decline
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            )}
        </div>
    );
}
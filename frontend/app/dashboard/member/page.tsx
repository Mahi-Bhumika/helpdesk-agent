"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";
import GlassCard from "@/components/GlassCard";
import PillBadge from "@/components/PillBadge";

type Member = {
    user_id: string;
    name: string | null;
    email: string;
    role: string;
    status: "pending" | "active" | "declined";   // was: string
    created_at: string;
};

export default function MembersPage() {
    const { tenantId, role, loading: authLoading } = useAuth();
    const router = useRouter();
    const [members, setMembers] = useState<Member[]>([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);

    // Owner-only guard — hiding the sidebar link isn't real access control,
    // this stops a regular member reaching the page via a direct URL.
    useEffect(() => {
        if (!authLoading && role !== "owner") {
            router.push("/dashboard");
        }
    }, [authLoading, role, router]);

    useEffect(() => {
        async function fetchMembers() {
            if (!tenantId || role !== "owner") return;
            setLoading(true);
            setError(null);
            const { data, error } = await supabase
                .from("users")
                .select("user_id, name, email, role, status, created_at")
                .eq("tenant_id", tenantId)
                .order("created_at", { ascending: true });

            if (error) setError(error.message);
            else setMembers(data ?? []);
            setLoading(false);
        }
        fetchMembers();
    }, [tenantId, role]);

    if (authLoading || role !== "owner") return null;

    return (
        <div className="p-8">
            <h1 className="text-2xl font-semibold text-text-primary mb-6">Members</h1>
            <GlassCard padding="lg">
                {loading && (
                    <div className="space-y-3">
                        {[...Array(4)].map((_, i) => (
                            <div key={i} className="h-10 w-full rounded-lg bg-white/[0.04] animate-pulse" />
                        ))}
                    </div>
                )}
                {!loading && error && <p className="text-sm text-status-declined">{error}</p>}
                {!loading && !error && members.length === 0 && (
                    <p className="text-sm text-text-secondary">No team members yet.</p>
                )}
                {!loading && !error && members.length > 0 && (
                    <table className="w-full text-sm">
                        <thead>
                            <tr className="text-left text-text-muted text-xs border-b border-white/[0.08]">
                                <th className="pb-2 font-medium">Name</th>
                                <th className="pb-2 font-medium">Email</th>
                                <th className="pb-2 font-medium">Role</th>
                                <th className="pb-2 font-medium">Status</th>
                                <th className="pb-2 font-medium">Joined</th>
                            </tr>
                        </thead>
                        <tbody>
                            {members.map((m, i) => (
                                <tr key={m.user_id} className={i % 2 === 0 ? "bg-white/[0.02]" : ""}>
                                    <td className="py-3 text-text-primary">{m.name || "—"}</td>
                                    <td className="py-3 text-text-secondary">{m.email}</td>
                                    <td className="py-3 text-text-secondary capitalize">{m.role}</td>
                                    <td className="py-3"><PillBadge status={m.status} /></td>
                                    <td className="py-3 text-text-secondary">
                                        {new Date(m.created_at).toLocaleDateString()}
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
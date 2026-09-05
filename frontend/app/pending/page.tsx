"use client"

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";

export default function PendingPage() {
    const { session, status, role, loading, refetchUserInfo } = useAuth();
    const router = useRouter();

    // Redirect immediately if already active (covers page load / refresh)
    useEffect(() => {
        if (loading) return;
        if (!session) {
            router.push("/login");
            return;
        }
        if (status === "active") {
            router.push(role === "owner" ? "/dashboard" : "/dashboard/member");
        }
    }, [loading, session, status, role, router]);

    // Poll every 15s while sitting on this page, in case an owner approves us mid-wait
    useEffect(() => {
        if (loading || !session) return;

        const interval = setInterval(() => {
            refetchUserInfo();
        }, 15000);

        return () => clearInterval(interval);
    }, [loading, session, refetchUserInfo]);

    const handleLogout = async () => {
        await supabase.auth.signOut();
        router.push("/login");
    };

    if (loading) {
        return <div className="flex min-h-screen items-center justify-center">Loading...</div>;
    }

    return (
        <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8 text-center">
            <h1 className="text-2xl font-bold">Waiting for approval</h1>
            <p className="max-w-sm text-sm text-gray-400">
                Your account has been created, but a team owner still needs to approve your access.
                You&apos;ll be able to log in normally once that happens.
            </p>
            <p className="text-xs text-gray-500">
                This page checks automatically every few seconds — no need to refresh.
            </p>
            <button onClick={handleLogout} className="text-sm text-gray-500 underline">
                Log out
            </button>
        </main>
    );
}
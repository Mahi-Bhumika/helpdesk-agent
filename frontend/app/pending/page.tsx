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
        return (
            <div className="flex min-h-screen items-center justify-center bg-gray-950">
                <p className="text-sm text-gray-400">Loading...</p>
            </div>
        );
    }

    return (
        <main className="flex min-h-screen items-center justify-center bg-gray-950 p-6">
            <div className="w-full max-w-md rounded-2xl border border-gray-800 bg-gray-900 p-8 text-center shadow-xl">
                <div className="mx-auto mb-6 flex h-14 w-14 items-center justify-center rounded-full bg-amber-500/10">
                    <span className="relative flex h-3 w-3">
                        <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-amber-400 opacity-75" />
                        <span className="relative inline-flex h-3 w-3 rounded-full bg-amber-500" />
                    </span>
                </div>

                <h1 className="text-2xl font-semibold text-white">Waiting for approval</h1>
                <p className="mt-3 text-sm leading-relaxed text-gray-400">
                    Your account has been created, but a team owner still needs to
                    approve your access before you can log in. You don&apos;t need to
                    do anything else — this page will move you along automatically
                    once that happens.
                </p>

                <p className="mt-6 flex items-center justify-center gap-2 text-xs text-gray-500">
                    <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-gray-500" />
                    Checking status automatically every few seconds
                </p>

                <button
                    onClick={handleLogout}
                    className="mt-8 text-sm text-gray-500 underline hover:text-gray-300"
                >
                    Log out
                </button>
            </div>
        </main>
    );
}
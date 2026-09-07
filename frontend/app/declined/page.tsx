"use client"

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";

export default function DeclinedPage() {
    const { session, status, loading } = useAuth();
    const router = useRouter();

    useEffect(() => {
        if (loading) return;
        if (!session) {
            router.push("/login");
            return;
        }
        // If somehow no longer declined (edge case — an owner reversed it manually
        // in the DB), don't leave them stuck here.
        if (status !== "declined") {
            router.push("/login");
        }
    }, [loading, session, status, router]);

    const handleLogout = async () => {
        await supabase.auth.signOut();
        router.push("/login");
    };

    if (loading) {
        return <div className="flex min-h-screen items-center justify-center">Loading...</div>;
    }

    return (
        <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8 text-center">
            <h1 className="text-2xl font-bold">Access request declined</h1>
            <p className="max-w-sm text-sm text-gray-400">
                The team owner did not approve your access request. If you believe this was a
                mistake, reach out to them directly.
            </p>
            <button onClick={handleLogout} className="text-sm text-gray-500 underline">
                Log out
            </button>
        </main>
    );
}
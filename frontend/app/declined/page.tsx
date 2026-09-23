"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";
import GlassCard from "@/components/GlassCard";
import Button from "@/components/Button";
import { XCircle } from "lucide-react";

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
        return (
            <main className="flex min-h-screen items-center justify-center bg-[#0B0B0C]">
                <p className="text-sm text-text-secondary">Loading...</p>
            </main>
        );
    }

    return (
        <main className="flex min-h-screen flex-col items-center justify-center bg-[#0B0B0C] p-6">
            <GlassCard padding="lg" className="max-w-sm w-full flex flex-col items-center text-center gap-5">
                <div className="flex h-14 w-14 items-center justify-center rounded-full bg-status-declined/10 ring-1 ring-status-declined/30">
                    <XCircle className="h-7 w-7 text-status-declined" />
                </div>

                <div className="space-y-2">
                    <h1 className="text-xl font-semibold text-text-primary">
                        Access request declined
                    </h1>
                    <p className="text-sm leading-relaxed text-text-secondary">
                        The team owner did not approve your access request. If you
                        believe this was a mistake, reach out to them directly.
                    </p>
                </div>

                <Button variant="ghost" onClick={handleLogout} className="mt-2">
                    Log out
                </Button>
            </GlassCard>
        </main>
    );
}
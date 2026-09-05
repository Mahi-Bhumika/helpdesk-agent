"use client"

import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { supabase } from "@/lib/supabase";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const { session, loading, role } = useAuth();
    const router = useRouter();

    useEffect(() => {
        if (!loading && !session) {
            router.push("/login");
        }
    }, [loading, session, router]);

    if (loading) {
        return <div className="flex min-h-screen items-center justify-center">Loading...</div>;
    }

    if (!session) {
        return null;
    }

    return (
        <div className="flex">
            <nav className="w-56 border-r p-4 flex flex-col">
                <a href="/dashboard/analytics">Analytics</a>
                <a href="/dashboard/settings">Bot Settings</a>
                {role === "owner" && (
                    <a href="/dashboard/embed">Embed Script</a>
                )}
                <a href="/dashboard/sessions">Chat Sessions</a>
                <a href="/dashboard/documents">Documents & FAQs</a>
                {/* TODO: Admin section, gated by role */}
                <button
                    onClick={async () => {
                        await supabase.auth.signOut();
                        router.push("/login");
                    }}
                    className="mt-4 text-left text-sm text-gray-400 underline"
                >
                    Log out
                </button>
            </nav>
            <main className="flex-1 p-6">{children}</main>
        </div>
    );
}
"use client"

import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const { session, loading, role } = useAuth();
    const router = useRouter();
    const [statusChecked, setStatusChecked] = useState(false);

    useEffect(() => {
        if (loading) return;

        if (!session) {
            router.push("/login");
            return;
        }

        const checkStatus = async () => {
            const { data: existingUser } = await supabase
                .from("users")
                .select("status")
                .eq("user_id", session.user.id)
                .maybeSingle();

            if (existingUser?.status !== "active") {
                router.push("/pending");
                return;
            }
            setStatusChecked(true);
        };
        checkStatus();
    }, [loading, session, router]);

    if (loading || !statusChecked) {
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
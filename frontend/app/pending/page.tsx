"use client"

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function PendingPage() {
    const router = useRouter();
    const [checking, setChecking] = useState(false);

    // If someone lands here who's already active (e.g. they got approved,
    // then revisited this page from a bookmark), bounce them to the real dashboard.
    useEffect(() => {
        const checkStatus = async () => {
            const { data: { user } } = await supabase.auth.getUser();
            if (!user) {
                router.push("/login");
                return;
            }
            const { data: existingUser } = await supabase
                .from("users")
                .select("status, role")
                .eq("user_id", user.id)
                .maybeSingle();

            if (existingUser?.status === "active") {
                router.push(existingUser.role === "owner" ? "/dashboard" : "/dashboard/member");
            }
        };
        checkStatus();
    }, [router]);

    const handleCheckAgain = async () => {
        setChecking(true);
        const { data: { user } } = await supabase.auth.getUser();
        if (!user) {
            router.push("/login");
            return;
        }
        const { data: existingUser } = await supabase
            .from("users")
            .select("status, role")
            .eq("user_id", user.id)
            .maybeSingle();

        if (existingUser?.status === "active") {
            router.push(existingUser.role === "owner" ? "/dashboard" : "/dashboard/member");
        } else {
            setChecking(false); // still pending, stay here
        }
    };

    const handleLogout = async () => {
        await supabase.auth.signOut();
        router.push("/login");
    };

    return (
        <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8 text-center">
            <h1 className="text-2xl font-bold">Waiting for approval</h1>
            <p className="max-w-sm text-sm text-gray-400">
                Your account has been created, but a team owner still needs to approve your access.
                You&apos;ll be able to log in normally once that happens.
            </p>
            <button
                onClick={handleCheckAgain}
                disabled={checking}
                className="rounded-md bg-black px-4 py-2 text-white hover:bg-gray-800 disabled:opacity-50"
            >
                {checking ? "Checking..." : "Check again"}
            </button>
            <button onClick={handleLogout} className="text-sm text-gray-500 underline">
                Log out
            </button>
        </main>
    );
}
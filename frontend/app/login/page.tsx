"use client"

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";

export default function LoginPage() {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const router = useRouter();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        const { error } = await supabase.auth.signInWithPassword({ email, password });

        if (error) {
            setError(error.message);
            return;
        }

        router.push("/dashboard/analytics");
    };

    return(
        <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8">
            <h1 className="text-2xl font-bold"> Log in </h1>
            <form onSubmit={handleSubmit} className="flex w-full max-w-sm flex-col gap-4">
                <input type="email" placeholder="Email" value={email} 
                onChange={(e) => setEmail(e.target.value)}
                className="rounded-md border border-gray-300 px-3 py-2"
                required
                />
                <input type="password" placeholder="Password" value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="rounded-md border border-gray-300 px-3 py-2"
                required
                />
                {error && <p className="text-sm text-red-600">{error}</p>}
                <button type="submit"
                className="rounded-md bg-black px-4 py-2 text-white hover:bg-gray-800"
                >
                    Log in
                </button>
            </form>
            <Link href='/' className="text-sm text-gray-500 underline">
            ← Back to home
            </Link>
        </main>
    );
}
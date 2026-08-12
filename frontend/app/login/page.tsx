"use client"

import Link from "next/link";
import { useState } from "react";

export default function LoginPage() {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");

    const handleSubmit  = (e: React.FormEvent) => {
        e.preventDefault(); // prevents the auto-refresh and adding email to url default 
        // no real auth : just pushed to console log for now
        console.log("Login attempt :", {email, password});
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
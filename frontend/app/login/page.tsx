"use client"

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import { useAuth } from "@/lib/auth-context";

export default function LoginPage() {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);
    const router = useRouter();
    const { refetchUserInfo } = useAuth();

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        const { data, error: signInError } = await supabase.auth.signInWithPassword({ email, password });
        if (signInError) {
            setError(signInError.message);
            return;
        }

        const { data: { session } } = await supabase.auth.getSession();
        const token = session?.access_token;

        const { data: existingUser } = await supabase
            .from("users")
            .select("tenant_id, status, role")
            .eq("user_id", data.user.id)
            .maybeSingle();

        if (!existingUser) {
            const metadata = data.user.user_metadata;

            if (metadata.invite_token) {
                const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/invite/accept`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                    body: JSON.stringify({
                        invite_token: metadata.invite_token,
                        user_id: data.user.id,
                        email: data.user.email,
                    }),
                });
                if (!res.ok) {
                    const detail = await res.text();
                    console.error("invite/accept failed:", res.status, detail);
                    setError("Could not join tenant. The invite link may be invalid or already used.");
                    return;
                }
                await refetchUserInfo(); // sync context before routing
                router.push("/pending");
            } else {
                const pendingData = JSON.parse(metadata.pending_tenant_setup || "{}");
                const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/tenants`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
                    body: JSON.stringify({
                        owner_id: data.user.id,
                        owner_email: data.user.email,
                        company_name: pendingData.companyName,
                        type_of_business: pendingData.typeOfBusiness,
                        subscription_plan: pendingData.subscriptionPlan,
                        bot_name: pendingData.botName,
                        greeting_message: pendingData.greetingMessage,
                        theme_color: pendingData.themeColor,
                    }),
                });
                if (!res.ok) {
                    const detail = await res.text();
                    console.error("/tenants failed:", res.status, detail);
                    setError("Account created, but tenant setup failed. Contact support.");
                    return;
                }
                await refetchUserInfo(); // <-- the actual fix: sync context before routing
                router.push("/dashboard");
            }
                } else {
            // Returning user — route by real status/role
            if (existingUser.status === "declined") {
                router.push("/declined");
            } else if (existingUser.status === "pending") {
                router.push("/pending");
            } else if (existingUser.role === "owner") {
                router.push("/dashboard");
            } else {
                router.push("/dashboard/member");
            }
        }
        
    };

    return (
        <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8">
            <h1 className="text-2xl font-bold"> Log in </h1>
            <form onSubmit={handleSubmit} className="flex w-full max-w-sm flex-col gap-4">
                <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} className="rounded-md border border-gray-300 px-3 py-2" required />
                <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} className="rounded-md border border-gray-300 px-3 py-2" required />
                {error && <p className="text-sm text-red-600">{error}</p>}
                <button type="submit" className="rounded-md bg-black px-4 py-2 text-white hover:bg-gray-800">Log in</button>
            </form>
            <Link href="/" className="text-sm text-gray-500 underline">← Back to home</Link>
        </main>
    );
}
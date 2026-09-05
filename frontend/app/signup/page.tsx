"use client"

import Link from "next/link";
import { useState } from "react";
import { useSearchParams } from "next/navigation";
import { supabase } from "@/lib/supabase";

type SignupForm = {
    email: string;
    password: string;
    companyName: string;
    typeOfBusiness: string;
    subscriptionPlan: string;
    botName: string;
    greetingMessage: string;
    themeColor: string;
};

export default function SignupPage() {
    const searchParams = useSearchParams();
    const inviteToken = searchParams.get("invite"); // null for owner signup, a real token for invited members

    const [formData, setFormData] = useState<SignupForm>({
        email: "",
        password: "",
        companyName: "",
        typeOfBusiness: "",
        subscriptionPlan: "",
        botName: "",
        greetingMessage: "",
        themeColor: "",
    });
    const [error, setError] = useState<string | null>(null);
    const [success, setSuccess] = useState(false);

    const handleChange =
        (field: keyof SignupForm) =>
        (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
            setFormData({ ...formData, [field]: e.target.value });
        };

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        const { data, error: authError } = await supabase.auth.signUp({
            email: formData.email,
            password: formData.password,
            options: {
                emailRedirectTo: `${window.location.origin}/login`,
                data: inviteToken
                    ? { invite_token: inviteToken }
                    : { pending_tenant_setup: JSON.stringify(formData) },
            },
        });

        if (authError) {
            setError(authError.message);
            return;
        }

        if (data.user?.identities?.length === 0) {
            setError("An account with this email already exists. Try logging in instead.");
            return;
        }

        // Tenant/invite linking now happens at first LOGIN (after email confirmation),
        // not here — signUp() doesn't return a usable session when confirmation is required,
        // so there's no token yet to safely authenticate that call.
        setSuccess(true);
    };

    return (
        <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8">
            <h1 className="text-2xl font-bold">
                {inviteToken ? "Join your team" : "Sign up"}
            </h1>

            {success ? (
                <div className="flex max-w-sm flex-col items-center gap-3 text-center">
                    <p className="text-lg font-medium">Check your inbox 📩</p>
                    <p className="text-sm text-gray-400">
                        We&apos;ve sent a verification link to{" "}
                        <span className="font-medium">{formData.email}</span>.
                        Click it to activate your account, then log in.
                    </p>
                    <Link href="/login" className="mt-2 text-sm text-gray-500 underline">
                        Go to login
                    </Link>
                </div>
            ) : (
                <form onSubmit={handleSubmit} className="flex w-full max-w-sm flex-col gap-4">
                    <input
                        type="email"
                        placeholder="Email"
                        value={formData.email}
                        onChange={handleChange("email")}
                        className="rounded-md border border-gray-300 px-3 py-2"
                        required
                    />
                    <input
                        type="password"
                        placeholder="Password"
                        value={formData.password}
                        onChange={handleChange("password")}
                        className="rounded-md border border-gray-300 px-3 py-2"
                        required
                    />

                    {/* Invited members are joining an existing tenant — they don't set up
                        company/bot details, that's the owner's job. Only show these fields
                        for a fresh owner signup (no invite token in the URL). */}
                    {!inviteToken && (
                        <>
                            <input
                                type="text"
                                placeholder="Company name"
                                value={formData.companyName}
                                onChange={handleChange("companyName")}
                                className="rounded-md border border-gray-300 px-3 py-2"
                                required
                            />
                            <input
                                type="text"
                                placeholder="Type of business (e.g. e-commerce, SaaS)"
                                value={formData.typeOfBusiness}
                                onChange={handleChange("typeOfBusiness")}
                                className="rounded-md border border-gray-300 px-3 py-2"
                            />
                            <input
                                type="text"
                                placeholder="Subscription plan"
                                value={formData.subscriptionPlan}
                                onChange={handleChange("subscriptionPlan")}
                                className="rounded-md border border-gray-300 px-3 py-2"
                            />
                            <input
                                type="text"
                                placeholder="Bot name"
                                value={formData.botName}
                                onChange={handleChange("botName")}
                                className="rounded-md border border-gray-300 px-3 py-2"
                            />
                            <textarea
                                placeholder="Bot greeting message"
                                value={formData.greetingMessage}
                                onChange={handleChange("greetingMessage")}
                                className="rounded-md border border-gray-300 px-3 py-2"
                            />
                            <input
                                type="text"
                                placeholder="Theme color (e.g. #4F46E5)"
                                value={formData.themeColor}
                                onChange={handleChange("themeColor")}
                                className="rounded-md border border-gray-300 px-3 py-2"
                            />
                        </>
                    )}

                    {error && <p className="text-sm text-red-600">{error}</p>}
                    <button
                        type="submit"
                        className="rounded-md bg-black px-4 py-2 text-white hover:bg-gray-800"
                    >
                        Sign up
                    </button>
                </form>
            )}

            <Link href="/" className="text-sm text-gray-500 underline">
                ← Back to home
            </Link>
        </main>
    );
}
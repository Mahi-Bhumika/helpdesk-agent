"use client"

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";
import { authedFetch } from "@/lib/api";
import GlassCard from "@/components/GlassCard";
import Button from "@/components/Button";

export default function SettingsPage() {
    const { tenantId } = useAuth();
    const [botName, setBotName] = useState("");
    const [greetingMessage, setGreetingMessage] = useState("");
    const [themeColor, setThemeColor] = useState("#7C3AED");
    const [websiteDomain, setWebsiteDomain] = useState("");

    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);
    const [savingDomain, setSavingDomain] = useState(false);
    const [domainSaved, setDomainSaved] = useState(false);
    const [fallbackMessage, setFallbackMessage] = useState("");

    useEffect(() => {
        async function fetchTenant() {
            if (!tenantId) return;
            const { data, error } = await supabase
                .from("tenants")
                .select("bot_name, greeting_message, theme_color, website_domain, fallback_message")
                .eq("tenant_id", tenantId)
                .single();

            if (!error && data) {
                setBotName(data.bot_name ?? "");
                setGreetingMessage(data.greeting_message ?? "");
                setThemeColor(data.theme_color ?? "#7C3AED");
                setWebsiteDomain(data.website_domain ?? "");
                setFallbackMessage(data.fallback_message ?? "");
            }
            setLoading(false);
        }
        fetchTenant();
    }, [tenantId]);

    const handleSave = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!tenantId) return;
        setSaving(true);
        setSaved(false);

        const { error } = await supabase
            .from("tenants")
            .update({
                bot_name: botName,
                greeting_message: greetingMessage,
                theme_color: themeColor,
                fallback_message: fallbackMessage,
            })
            .eq("tenant_id", tenantId);

        setSaving(false);
        if (!error) setSaved(true);
    };

    const handleSaveWebsiteDomain = async () => {
        setSavingDomain(true);
        setDomainSaved(false);

        const res = await authedFetch("/tenants/website-domain", {
            method: "PUT",
            body: JSON.stringify({ website_domain: websiteDomain }),
        });

        setSavingDomain(false);
        if (!res.ok) {
            console.error("Failed to save website domain");
            return;
        }
        setDomainSaved(true);
    };

    if (!tenantId || loading) {
        return <div className="p-8 text-text-secondary">Loading settings...</div>;
    }

    return (
        <div className="p-8">
            <h1 className="text-2xl font-semibold text-text-primary mb-6">Bot Settings</h1>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <div className="flex flex-col gap-6">
                    <GlassCard padding="lg">
                        <form onSubmit={handleSave} className="flex flex-col gap-4">
                            <label className="flex flex-col gap-1.5">
                                <span className="text-sm text-text-secondary">Bot name</span>
                                <input
                                    type="text"
                                    value={botName}
                                    onChange={(e) => setBotName(e.target.value)}
                                    className="rounded-lg border border-white/[0.1] bg-white/[0.05] px-3 py-2.5 text-sm text-text-primary"
                                />
                            </label>
                            <label className="flex flex-col gap-1.5">
                                <span className="text-sm text-text-secondary">Greeting message</span>
                                <textarea
                                    value={greetingMessage}
                                    onChange={(e) => setGreetingMessage(e.target.value)}
                                    rows={3}
                                    className="rounded-lg border border-white/[0.1] bg-white/[0.05] px-3 py-2.5 text-sm text-text-primary"
                                />
                            </label>
                            <label className="flex flex-col gap-1.5">
                                <span className="text-sm text-text-secondary">Fallback message</span>
                                <textarea
                                    value={fallbackMessage}
                                    onChange={(e) => setFallbackMessage(e.target.value)}
                                    rows={2}
                                    placeholder="Sorry, I don't have an answer for that — try rephrasing or contact support."
                                    className="rounded-lg border border-white/[0.1] bg-white/[0.05] px-3 py-2.5 text-sm text-text-primary"
                                />
                            </label>
                            <label className="flex flex-col gap-1.5">
                                <span className="text-sm text-text-secondary">Theme color</span>
                                <input
                                    type="color"
                                    value={themeColor}
                                    onChange={(e) => setThemeColor(e.target.value)}
                                    className="h-10 w-20 rounded-lg border border-white/[0.1] bg-transparent"
                                />
                            </label>
                            <Button type="submit" disabled={saving}>
                                {saving ? "Saving..." : "Save changes"}
                            </Button>
                            {saved && <p className="text-sm text-status-active">Saved ✓</p>}
                        </form>
                    </GlassCard>

                    <GlassCard padding="lg">
                        <label className="flex flex-col gap-1.5">
                            <span className="text-sm text-text-secondary">Your website domain</span>
                            <input
                                type="text"
                                value={websiteDomain}
                                onChange={(e) => setWebsiteDomain(e.target.value)}
                                placeholder="yourcompany.com"
                                className="rounded-lg border border-white/[0.1] bg-white/[0.05] px-3 py-2.5 text-sm text-text-primary"
                            />
                        </label>
                        <p className="text-xs text-text-muted mt-1.5 mb-4">
                            The domain where your chat widget is embedded. Required for the widget to work.
                        </p>
                        <Button variant="secondary" onClick={handleSaveWebsiteDomain} disabled={savingDomain}>
                            {savingDomain ? "Saving..." : "Save"}
                        </Button>
                        {domainSaved && <p className="text-sm text-status-active mt-2">Saved ✓</p>}
                    </GlassCard>
                </div>

                {/* Live widget preview */}
                <GlassCard padding="lg" className="h-fit">
                    <p className="text-sm text-text-secondary mb-4">Widget preview</p>
                    <div className="rounded-xl2 bg-obsidian-surface border border-white/[0.08] p-4 flex flex-col gap-3 h-80">
                        <div
                            className="self-start max-w-[85%] rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm text-white"
                            style={{ backgroundColor: themeColor }}
                        >
                            {greetingMessage || "Hi! How can I help you today?"}
                        </div>
                        <div className="self-end max-w-[85%] rounded-2xl rounded-br-sm px-4 py-2.5 text-sm bg-white/[0.08] text-text-primary">
                            What are your business hours?
                        </div>
                    </div>
                    <p className="text-xs text-text-muted mt-3 text-center">
                        {botName || "Your bot"}'s greeting, shown as visitors will see it
                    </p>
                </GlassCard>
            </div>
        </div>
    );
}
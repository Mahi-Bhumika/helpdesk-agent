"use client"

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";
import { authedFetch } from "@/lib/api";
import GlassCard from "@/components/GlassCard";
import Button from "@/components/Button";

type TenantSettings = {
    bot_name: string;
    greeting_message: string;
    theme_color: string;
    fallback_message: string;
};

export default function SettingsPage() {
    const { tenantId } = useAuth();

    const [saved, setSavedSettings] = useState<TenantSettings>({
        bot_name: "",
        greeting_message: "",
        theme_color: "#7C3AED",
        fallback_message: "",
    });
    const [draft, setDraft] = useState<TenantSettings>(saved);
    const [isEditing, setIsEditing] = useState(false);

    const [websiteDomain, setWebsiteDomain] = useState("");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [justSaved, setJustSaved] = useState(false);
    const [savingDomain, setSavingDomain] = useState(false);
    const [domainSaved, setDomainSaved] = useState(false);

    useEffect(() => {
        async function fetchTenant() {
            if (!tenantId) return;
            const { data, error } = await supabase
                .from("tenants")
                .select("bot_name, greeting_message, theme_color, website_domain, fallback_message")
                .eq("tenant_id", tenantId)
                .single();

            if (!error && data) {
                const loaded = {
                    bot_name: data.bot_name ?? "",
                    greeting_message: data.greeting_message ?? "",
                    theme_color: data.theme_color ?? "#7C3AED",
                    fallback_message: data.fallback_message ?? "",
                };
                setSavedSettings(loaded);
                setDraft(loaded);
                setWebsiteDomain(data.website_domain ?? "");
            }
            setLoading(false);
        }
        fetchTenant();
    }, [tenantId]);

    const handleSave = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!tenantId) return;
        setSaving(true);
        setJustSaved(false);

        const { error } = await supabase
            .from("tenants")
            .update(draft)
            .eq("tenant_id", tenantId);

        setSaving(false);
        if (!error) {
            setSavedSettings(draft);
            setJustSaved(true);
            setIsEditing(false);
        }
    };

    const handleCancel = () => {
        setDraft(saved); // discard unsaved edits
        setIsEditing(false);
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
                        {!isEditing ? (
                            <div className="flex flex-col gap-4">
                                <div>
                                    <span className="text-sm text-text-secondary">Bot name</span>
                                    <p className="text-text-primary mt-0.5">{saved.bot_name || "—"}</p>
                                </div>
                                <div>
                                    <span className="text-sm text-text-secondary">Greeting message</span>
                                    <p className="text-text-primary mt-0.5">{saved.greeting_message || "—"}</p>
                                </div>
                                <div>
                                    <span className="text-sm text-text-secondary">Fallback message</span>
                                    <p className="text-text-primary mt-0.5">{saved.fallback_message || "—"}</p>
                                </div>
                                <div>
                                    <span className="text-sm text-text-secondary">Theme color</span>
                                    <div className="flex items-center gap-2 mt-1">
                                        <span
                                            className="h-6 w-6 rounded-full border border-white/[0.15]"
                                            style={{ backgroundColor: saved.theme_color }}
                                        />
                                        <span className="text-text-primary text-sm">{saved.theme_color}</span>
                                    </div>
                                </div>
                                <Button onClick={() => setIsEditing(true)} className="w-fit">
                                    Edit
                                </Button>
                                {justSaved && <p className="text-sm text-status-active">Saved ✓</p>}
                            </div>
                        ) : (
                            <form onSubmit={handleSave} className="flex flex-col gap-4">
                                <label className="flex flex-col gap-1.5">
                                    <span className="text-sm text-text-secondary">Bot name</span>
                                    <input
                                        type="text"
                                        value={draft.bot_name}
                                        onChange={(e) => setDraft({ ...draft, bot_name: e.target.value })}
                                        className="rounded-lg border border-white/[0.1] bg-white/[0.05] px-3 py-2.5 text-sm text-text-primary"
                                    />
                                </label>
                                <label className="flex flex-col gap-1.5">
                                    <span className="text-sm text-text-secondary">Greeting message</span>
                                    <textarea
                                        value={draft.greeting_message}
                                        onChange={(e) => setDraft({ ...draft, greeting_message: e.target.value })}
                                        rows={3}
                                        className="rounded-lg border border-white/[0.1] bg-white/[0.05] px-3 py-2.5 text-sm text-text-primary"
                                    />
                                </label>
                                <label className="flex flex-col gap-1.5">
                                    <span className="text-sm text-text-secondary">Fallback message</span>
                                    <textarea
                                        value={draft.fallback_message}
                                        onChange={(e) => setDraft({ ...draft, fallback_message: e.target.value })}
                                        rows={2}
                                        placeholder="Sorry, I don't have an answer for that — try rephrasing or contact support."
                                        className="rounded-lg border border-white/[0.1] bg-white/[0.05] px-3 py-2.5 text-sm text-text-primary"
                                    />
                                </label>
                                <label className="flex flex-col gap-1.5">
                                    <span className="text-sm text-text-secondary">Theme color</span>
                                    <input
                                        type="color"
                                        value={draft.theme_color}
                                        onChange={(e) => setDraft({ ...draft, theme_color: e.target.value })}
                                        className="h-10 w-20 rounded-lg border border-white/[0.1] bg-transparent"
                                    />
                                </label>
                                <div className="flex gap-2">
                                    <Button type="submit" disabled={saving}>
                                        {saving ? "Saving..." : "Save changes"}
                                    </Button>
                                    <Button type="button" variant="secondary" onClick={handleCancel} disabled={saving}>
                                        Cancel
                                    </Button>
                                </div>
                            </form>
                        )}
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

                <GlassCard padding="lg" className="h-fit">
                    <p className="text-sm text-text-secondary mb-4">Widget preview</p>
                    <div className="rounded-xl2 border border-white/[0.08] overflow-hidden h-80 flex flex-col">
                        <div
                            className="flex items-center justify-between px-4 py-3 flex-shrink-0"
                            style={{ backgroundColor: isEditing ? draft.theme_color : saved.theme_color }}
                        >
                            <span className="text-sm font-semibold text-white">
                                {(isEditing ? draft.bot_name : saved.bot_name) || "Your bot"}
                            </span>
                            <div className="flex items-center gap-2">
                                <span className="text-[11px] font-medium text-white/90 bg-white/20 rounded-full px-2.5 py-1">
                                    End Chat
                                </span>
                                <span className="text-white/85 text-sm leading-none">✕</span>
                            </div>
                        </div>

                        <div className="flex-1 bg-obsidian-surface p-4 flex flex-col gap-3 overflow-y-auto">
                            <div className="flex flex-col items-start max-w-[85%]">
                                <div
                                    className="rounded-2xl rounded-bl-sm px-4 py-2.5 text-sm text-white"
                                    style={{ backgroundColor: isEditing ? draft.theme_color : saved.theme_color }}
                                >
                                    {(isEditing ? draft.greeting_message : saved.greeting_message) || "Hi! How can I help you today?"}
                                </div>
                                <span className="text-[10.5px] text-text-muted mt-1 px-1">10:05 AM</span>
                            </div>

                            <div className="flex flex-col items-end self-end max-w-[85%]">
                                <div className="rounded-2xl rounded-br-sm px-4 py-2.5 text-sm bg-white/[0.08] text-text-primary">
                                    What are your business hours?
                                </div>
                                <span className="text-[10.5px] text-text-muted mt-1 px-1">10:05 AM</span>
                            </div>
                        </div>
                    </div>
                    <p className="text-xs text-text-muted mt-3 text-center">
                        {(isEditing ? draft.bot_name : saved.bot_name) || "Your bot"}'s greeting, shown as visitors will see it
                    </p>
                </GlassCard>
            </div>
        </div>
    );
}
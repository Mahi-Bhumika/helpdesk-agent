"use client"

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";

export default function SettingsPage() {
    const { tenantId } = useAuth();
    const [botName, setBotName] = useState("");
    const [greetingMessage, setGreetingMessage] = useState("");
    const [themeColor, setThemeColor] = useState("#000000");
    const [loading, setLoading] = useState(true);
    const [saving, setSaving] = useState(false);
    const [saved, setSaved] = useState(false);

    useEffect(() => {
        async function fetchTenant() {
            if (!tenantId) return;
            const { data, error } = await supabase
                .from("tenants")
                .select("bot_name, greeting_message, theme_color")
                .eq("tenant_id", tenantId)
                .single();

            if (!error && data) {
                setBotName(data.bot_name ?? "");
                setGreetingMessage(data.greeting_message ?? "");
                setThemeColor(data.theme_color ?? "#000000");
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
            })
            .eq("tenant_id", tenantId);

        setSaving(false);
        if (!error) setSaved(true);
    };

    if (!tenantId || loading) {
        return <div>Loading settings...</div>;
    }

    return (
        <div>
            <h1 className="text-xl font-bold mb-6">Bot Settings</h1>
            <form onSubmit={handleSave} className="flex max-w-sm flex-col gap-4">
                <label className="flex flex-col gap-1">
                    <span className="text-sm text-gray-400">Bot name</span>
                    <input
                        type="text"
                        value={botName}
                        onChange={(e) => setBotName(e.target.value)}
                        className="rounded-md border border-gray-300 px-3 py-2"
                    />
                </label>
                <label className="flex flex-col gap-1">
                    <span className="text-sm text-gray-400">Greeting message</span>
                    <textarea
                        value={greetingMessage}
                        onChange={(e) => setGreetingMessage(e.target.value)}
                        className="rounded-md border border-gray-300 px-3 py-2"
                    />
                </label>
                <label className="flex flex-col gap-1">
                    <span className="text-sm text-gray-400">Theme color</span>
                    <input
                        type="color"
                        value={themeColor}
                        onChange={(e) => setThemeColor(e.target.value)}
                        className="h-10 w-20 rounded-md border border-gray-300"
                    />
                </label>
                <button
                    type="submit"
                    disabled={saving}
                    className="rounded-md bg-black px-4 py-2 text-white hover:bg-gray-800"
                >
                    {saving ? "Saving..." : "Save changes"}
                </button>
                {saved && <p className="text-sm text-green-500">Saved ✓</p>}
            </form>
        </div>
    );
}
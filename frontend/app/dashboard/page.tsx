"use client";

import { useEffect, useState } from "react";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";
import Link from "next/link";

export default function DashboardHome() {
    const { tenantId } = useAuth();
    const [websiteDomain, setWebsiteDomain] = useState<string | null>(null);

    useEffect(() => {
        async function fetchDomain() {
            if (!tenantId) return;
            const { data } = await supabase
                .from("tenants")
                .select("website_domain")
                .eq("tenant_id", tenantId)
                .single();
            setWebsiteDomain(data?.website_domain ?? null);
        }
        fetchDomain();
    }, [tenantId]);

    return (
        <div>
            <h1 className="text-xl font-bold mb-4">Dashboard</h1>

            <div className="flex flex-wrap gap-3 mb-6">
                <Link href="/dashboard/sessions" className="text-sm border border-gray-700 rounded-md px-3 py-2 hover:bg-gray-900">
                    View chat sessions →
                </Link>
                <Link href="/dashboard/analytics" className="text-sm border border-gray-700 rounded-md px-3 py-2 hover:bg-gray-900">
                    View analytics →
                </Link>
                {websiteDomain && (
                <a
                href={websiteDomain.startsWith("http") ? websiteDomain : `https://${websiteDomain}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-sm border border-gray-700 rounded-md px-3 py-2 hover:bg-gray-900"
                >
                Try your bot on your site ↗
                </a>
            )}
            </div>
            {/* rest of your existing dashboard home content, if any */}
        </div>
    );
}
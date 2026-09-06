"use client";

import { useAuth } from "@/lib/auth-context";

export default function MemberDashboardPage() {
    const { role, tenantId } = useAuth();

    return (
        <div>
            <h1 className="text-xl font-bold mb-2">Welcome</h1>
            <p className="text-sm text-gray-400">
                You&apos;re logged in as a team member.
            </p>
            {/* Debug info — remove once this is a real page, useful for
                confirming the redirect actually landed with correct data
                during Friday's approval test */}
            <p className="mt-4 text-xs text-gray-600">
                role: {role} · tenant: {tenantId}
            </p>
        </div>
    );
}
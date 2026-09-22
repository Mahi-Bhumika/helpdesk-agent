"use client";

import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/lib/auth-context";
import { authedFetch } from "@/lib/api";
import { useRouter } from "next/navigation";
import { supabase } from "@/lib/supabase";
import GlassCard from "@/components/GlassCard";
import Button from "@/components/Button";

type PendingUser = {
  user_id: string;
  email: string;
  invited_at: string | null;
  created_at: string;
};

export default function InvitesAdminPage() {
  const { role, loading: authLoading, tenantId } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!authLoading && role !== "owner") {
      router.push("/dashboard/member");
    }
  }, [authLoading, role, router]);

  const [pending, setPending] = useState<PendingUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [actioningId, setActioningId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Invite link state
  const [inviteToken, setInviteToken] = useState<string | null>(null);
  const [inviteLoading, setInviteLoading] = useState(true);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!tenantId) return;

    const fetchInviteToken = async () => {
      const { data, error: tokenError } = await supabase
        .from("tenants")
        .select("invite_token")
        .eq("tenant_id", tenantId)
        .maybeSingle();

      if (tokenError || !data) {
        console.error("Could not fetch invite token:", tokenError);
        setInviteLoading(false);
        return;
      }
      setInviteToken(data.invite_token);
      setInviteLoading(false);
    };

    fetchInviteToken();
  }, [tenantId]);

  const inviteUrl =
    inviteToken && typeof window !== "undefined"
      ? `${window.location.origin}/signup?invite=${inviteToken}`
      : null;

  const handleCopy = async () => {
    if (!inviteUrl) return;
    await navigator.clipboard.writeText(inviteUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const fetchPending = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await authedFetch("/admin/pending-users", { method: "GET" });
      if (!res.ok) throw new Error(`Failed to load pending users (${res.status})`);
      const data = await res.json();
      setPending(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPending();
  }, [fetchPending]);

  const handleDecision = async (userId: string, action: "approve" | "decline") => {
    setActioningId(userId);
    setError(null);
    try {
      const res = await authedFetch(`/admin/${action}-user`, {
        method: "POST",
        body: JSON.stringify({ user_id: userId }),
      });
      if (!res.ok) throw new Error(`Failed to ${action} user (${res.status})`);
      await fetchPending();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setActioningId(null);
    }
  };

  if (loading) return <div className="p-8 text-sm text-text-secondary">Loading pending requests...</div>;

  return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold text-text-primary mb-6">Invites</h1>

      {/* Invite link section */}
      <GlassCard padding="lg" className="mb-8">
        <h2 className="text-sm font-medium text-text-secondary mb-3">
          Team invite link
        </h2>
        {inviteLoading ? (
          <div className="h-10 w-full rounded-lg bg-white/[0.04] animate-pulse" />
        ) : inviteUrl ? (
          <div className="flex items-center gap-2">
            <input
              type="text"
              readOnly
              value={inviteUrl}
              onClick={(e) => e.currentTarget.select()}
              className="flex-1 rounded-lg border border-white/[0.1] bg-obsidian-surface px-3 py-2.5 text-sm text-text-primary"
            />
            <Button variant="secondary" onClick={handleCopy} className="whitespace-nowrap">
              {copied ? "Copied ✓" : "Copy"}
            </Button>
          </div>
        ) : (
          <p className="text-sm text-status-declined">
            No invite token found for this tenant.
          </p>
        )}
        <p className="mt-3 text-xs text-text-muted">
          Anyone with this link can request to join your team. They&apos;ll
          show up below once they sign up, waiting on your approval.
        </p>
      </GlassCard>

      {/* Pending requests */}
      <h2 className="text-lg font-medium text-text-primary mb-3">Pending requests</h2>

      {error && (
        <p className="mb-4 text-sm text-status-declined">{error}</p>
      )}

      <GlassCard padding="none">
        {pending.length === 0 ? (
          <p className="p-12 text-center text-sm text-text-secondary">
            No pending requests.
          </p>
        ) : (
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-white/[0.08]">
                <th className="px-6 py-4 text-xs font-medium text-text-secondary">Email</th>
                <th className="px-6 py-4 text-xs font-medium text-text-secondary">Requested</th>
                <th className="px-6 py-4 text-xs font-medium text-text-secondary">Action</th>
              </tr>
            </thead>
            <tbody>
              {pending.map((u) => (
                <tr key={u.user_id} className="row-alt border-b border-white/[0.04] hover:bg-white/[0.03]">
                  <td className="px-6 py-4 text-sm text-text-primary">{u.email}</td>
                  <td className="px-6 py-4 text-sm text-text-secondary">
                    {new Date(u.invited_at ?? u.created_at).toLocaleString()}
                  </td>
                  <td className="px-6 py-4 flex items-center gap-2">
                    <Button
                      size="sm"
                      disabled={actioningId === u.user_id}
                      onClick={() => handleDecision(u.user_id, "approve")}
                      className="bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow-sm transition-colors border-none"
                    >
                      Accept
                    </Button>
                    <Button
                        size="sm"
                        disabled={actioningId === u.user_id}
                        onClick={() => handleDecision(u.user_id, "decline")}
                        className="bg-[#2A1D1F] hover:bg-[#382427] text-[#F87171] border border-[#5C2B2E] rounded-xl transition-colors"
                    >
                        Decline
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </GlassCard>
    </div>
  );
}
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  BarChart3,
  MessageSquare,
  ExternalLink,
  ArrowRight,
  Sparkles,
  FileText,
} from "lucide-react";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";
import GlassCard from "@/components/GlassCard";

interface RecentSession {
  session_id: string;
  start_datetime: string;
  message_count: number;
}

function normalizeUrl(domain: string): string {
  return domain.startsWith("http://") || domain.startsWith("https://")
    ? domain
    : `https://${domain}`;
}

function LivePill() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium bg-status-activeSoft text-status-active">
      <span className="relative flex h-2 w-2">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-status-active opacity-75" />
        <span className="relative inline-flex rounded-full h-2 w-2 bg-status-active" />
      </span>
      Live
    </span>
  );
}

const QUICK_ACTIONS = [
  {
    href: "/dashboard/sessions",
    icon: MessageSquare,
    title: "View chat sessions",
    subtitle: "See every conversation your bot's had",
  },
  {
    href: "/dashboard/analytics",
    icon: BarChart3,
    title: "View analytics",
    subtitle: "Sessions, messages, and trends over time",
  },
  {
    href: "/dashboard/documents",
    icon: FileText,
    title: "Manage documents",
    subtitle: "Upload or review your bot's knowledge base",
  },
];

export default function DashboardOverviewPage() {
  const { tenantId } = useAuth();
  const [websiteDomain, setWebsiteDomain] = useState<string | null>(null);
  const [sessionCount, setSessionCount] = useState<number | null>(null);
  const [messageCount, setMessageCount] = useState<number | null>(null);
  const [recentSessions, setRecentSessions] = useState<RecentSession[] | null>(null);

  // Captured once on mount so timeAgo() below doesn't call Date.now()
  // directly during render (react-hooks/purity). Tradeoff: "x ago" labels
  // freeze at page-load time instead of ticking forward live — acceptable
  // for a recent-activity list, per Mahi's ok.
  const [now] = useState<number | null>(() => Date.now());

  useEffect(() => {
    if (!tenantId) return;

    async function load() {
      const [{ data: tenantRow }, { count: sCount }, { count: mCount }] = await Promise.all([
        supabase
          .from("tenants")
          .select("website_domain")
          .eq("tenant_id", tenantId)
          .maybeSingle(),
        supabase
          .from("chat_sessions")
          .select("*", { count: "exact", head: true })
          .eq("tenant_id", tenantId),
        supabase
          .from("messages")
          .select("*", { count: "exact", head: true })
          .eq("tenant_id", tenantId),
      ]);

      setWebsiteDomain(tenantRow?.website_domain ?? null);
      setSessionCount(sCount ?? 0);
      setMessageCount(mCount ?? 0);

      const { data: sessionRows } = await supabase
        .from("chat_sessions")
        .select("session_id, start_datetime")
        .eq("tenant_id", tenantId)
        .order("start_datetime", { ascending: false })
        .limit(3);

      if (sessionRows && sessionRows.length > 0) {
        const ids = sessionRows.map((s) => s.session_id);
        const { data: msgRows } = await supabase
          .from("messages")
          .select("session_id")
          .in("session_id", ids);

        const counts = new Map<string, number>();
        (msgRows ?? []).forEach((m) =>
          counts.set(m.session_id, (counts.get(m.session_id) ?? 0) + 1)
        );

        setRecentSessions(
          sessionRows.map((s) => ({
            session_id: s.session_id,
            start_datetime: s.start_datetime,
            message_count: counts.get(s.session_id) ?? 0,
          }))
        );
      } else {
        setRecentSessions([]);
      }
    }

    load();
  }, [tenantId]);

  function timeAgo(iso: string) {
    if (!now) return "";
    const diffMins = Math.round((now - new Date(iso).getTime()) / 60000);
    if (diffMins < 1) return "just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.round(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return `${Math.round(diffHours / 24)}d ago`;
  }

  return (
    <div className="p-8">
      {/* Hero */}
      <GlassCard glow padding="lg" className="mb-8 relative overflow-hidden">
        <div className="absolute -top-24 -right-24 h-64 w-64 rounded-full bg-gradient-brand opacity-20 blur-3xl pointer-events-none" />
        <div className="relative flex items-center justify-between flex-wrap gap-4">
          <div>
            <div className="flex items-center gap-3 mb-2">
              <Sparkles className="h-5 w-5 text-accent-violet" />
              <h1 className="text-2xl font-semibold text-text-primary">Welcome back</h1>
            </div>
            <div className="flex items-center gap-3">
              <LivePill />
              {websiteDomain && (
                <span className="text-sm text-text-secondary">
                  serving <span className="text-text-primary">{websiteDomain}</span>
                </span>
              )}
            </div>
          </div>

          {websiteDomain && (
            
             <a href={normalizeUrl(websiteDomain)}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 rounded-lg px-4 py-2.5 text-sm font-medium bg-gradient-brand text-white shadow-glow hover:brightness-110 transition-all"
            >
              Try your bot on your site
              <ExternalLink className="h-4 w-4" />
            </a>
          )}
        </div>
      </GlassCard>

      {/* Stat cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-6 mb-8">
        <GlassCard padding="lg">
          <div className="flex items-start justify-between mb-1">
            <span className="text-sm text-text-secondary">Chat sessions</span>
            <MessageSquare className="h-4 w-4 text-text-muted" />
          </div>
          <span className="text-3xl font-semibold text-text-primary">
            {sessionCount ?? <span className="inline-block h-8 w-12 rounded bg-white/[0.06] animate-pulse" />}
          </span>
        </GlassCard>

        <GlassCard padding="lg">
          <div className="flex items-start justify-between mb-1">
            <span className="text-sm text-text-secondary">Total messages</span>
            <BarChart3 className="h-4 w-4 text-text-muted" />
          </div>
          <span className="text-3xl font-semibold text-text-primary">
            {messageCount ?? <span className="inline-block h-8 w-12 rounded bg-white/[0.06] animate-pulse" />}
          </span>
        </GlassCard>
      </div>

      {/* Quick actions */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8">
        {QUICK_ACTIONS.map(({ href, icon: Icon, title, subtitle }) => (
          <Link key={href} href={href}>
            <GlassCard interactive padding="lg" className="h-full group">
              <div className="flex items-center justify-between mb-3">
                <div className="h-9 w-9 rounded-lg bg-gradient-brand-soft flex items-center justify-center">
                  <Icon className="h-4.5 w-4.5 text-accent-violet" />
                </div>
                <ArrowRight className="h-4 w-4 text-text-muted group-hover:text-text-primary group-hover:translate-x-0.5 transition-all" />
              </div>
              <p className="text-sm font-medium text-text-primary">{title}</p>
              <p className="text-xs text-text-secondary mt-1">{subtitle}</p>
            </GlassCard>
          </Link>
        ))}
      </div>

      {/* Recent activity */}
      <div>
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-lg font-medium text-text-primary">Recent activity</h2>
          <Link href="/dashboard/sessions" className="text-sm text-accent-violet hover:underline">
            View all →
          </Link>
        </div>

        <GlassCard padding="none">
          {recentSessions === null && (
            <div className="p-6 space-y-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="h-10 w-full rounded-md bg-white/[0.04] animate-pulse" />
              ))}
            </div>
          )}

          {recentSessions && recentSessions.length === 0 && (
            <p className="p-10 text-center text-sm text-text-secondary">
              No conversations yet — once your widget is live, they&apos;ll show up here.
            </p>
          )}

          {recentSessions && recentSessions.length > 0 && (
            <div>
              {recentSessions.map((s, i) => (
                <Link
                  key={s.session_id}
                  href={`/dashboard/sessions/${s.session_id}`}
                  className={`flex items-center justify-between px-6 py-4 hover:bg-white/[0.03] transition-colors ${
                    i !== recentSessions.length - 1 ? "border-b border-white/[0.06]" : ""
                  }`}
                >
                  <span className="text-sm text-text-primary">{timeAgo(s.start_datetime)}</span>
                  <span className="text-sm text-text-secondary">{s.message_count} messages</span>
                </Link>
              ))}
            </div>
          )}
        </GlassCard>
      </div>
    </div>
  );
}

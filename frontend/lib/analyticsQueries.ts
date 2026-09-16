import { SupabaseClient } from "@supabase/supabase-js";

export interface DailyCount {
  date: string;   // "MMM d" for display, e.g. "Sep 12"
  isoDate: string; // "2026-09-12", used for sorting/keying
  count: number;
}

/**
 * Builds a zero-filled array of the last `daysBack` days (including today),
 * so a day with zero sessions/messages still shows as a 0 point on the chart
 * instead of a gap.
 */
function buildEmptyDayBuckets(daysBack: number): Map<string, DailyCount> {
  const buckets = new Map<string, DailyCount>();
  const now = new Date();

  for (let i = daysBack - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(now.getDate() - i);
    const isoDate = d.toISOString().slice(0, 10); // "YYYY-MM-DD"
    const label = d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
    buckets.set(isoDate, { date: label, isoDate, count: 0 });
  }

  return buckets;
}

/**
 * Fetches chat_sessions.created_at for the current tenant (RLS already scopes this)
 * over the last `daysBack` days, and groups them into daily counts.
 */
export async function fetchSessionsPerDay(
  supabase: SupabaseClient,
  daysBack: number = 14
): Promise<DailyCount[]> {
  const since = new Date();
  since.setDate(since.getDate() - daysBack);

  const { data, error } = await supabase
    .from("chat_sessions")
    .select("created_at")
    .gte("created_at", since.toISOString());

  if (error) throw error;

  const buckets = buildEmptyDayBuckets(daysBack);

  for (const row of data ?? []) {
    const isoDate = new Date(row.created_at).toISOString().slice(0, 10);
    const bucket = buckets.get(isoDate);
    if (bucket) bucket.count += 1;
  }

  return Array.from(buckets.values());
}

/**
 * Same pattern as above, but for messages. If your messages table uses a
 * different timestamp column name, change "created_at" below to match.
 */
export async function fetchMessagesPerDay(
  supabase: SupabaseClient,
  daysBack: number = 14
): Promise<DailyCount[]> {
  const since = new Date();
  since.setDate(since.getDate() - daysBack);

  const { data, error } = await supabase
    .from("messages")
    .select("created_at")
    .gte("created_at", since.toISOString());

  if (error) throw error;

  const buckets = buildEmptyDayBuckets(daysBack);

  for (const row of data ?? []) {
    const isoDate = new Date(row.created_at).toISOString().slice(0, 10);
    const bucket = buckets.get(isoDate);
    if (bucket) bucket.count += 1;
  }

  return Array.from(buckets.values());
}


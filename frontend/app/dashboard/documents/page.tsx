"use client"

import { useDropzone } from "react-dropzone";
import { useEffect, useState, useCallback, useRef } from "react";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";
import { authedFetch } from "@/lib/api";
import GlassCard from "@/components/GlassCard";

type Doc = {
    document_id: string;
    file_url: string | null;
    format: string | null;
    theme: string | null;
    status: string;
    created_at: string;
};

const CATEGORY_OPTIONS = [
    { value: "faq", label: "FAQ" },
    { value: "manuals", label: "Manuals" },
    { value: "refund_policy", label: "Refund / Return Policy" },
    { value: "tos_privacy", label: "ToS / Privacy" },
    { value: "pricing", label: "Pricing Sheets" },
    { value: "onboarding", label: "Onboarding Guides" },
    { value: "kb_export", label: "KB Exports" },
] as const;

function categoryLabel(value: string | null) {
    return CATEGORY_OPTIONS.find((opt) => opt.value === value)?.label ?? value ?? "—";
}

function StatusPill({ status }: { status: string }) {
    const styles: Record<string, string> = {
        ready: "bg-status-activeSoft text-status-active shadow-glow-emerald",
        uploaded: "bg-status-pendingSoft text-status-pending shadow-glow-amber",
        processing: "bg-status-pendingSoft text-status-pending shadow-glow-amber",
        failed: "bg-status-declinedSoft text-status-declined",
    };
    const style = styles[status] ?? "bg-status-completedSoft text-status-completed shadow-glow-blue";

    return (
        <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${style}`}>
            <span className="h-1.5 w-1.5 rounded-full bg-current" />
            {status}
        </span>
    );
}

const STATUS_POLL_INTERVAL_MS = 1500;

export default function DocumentsPage() {
    const { tenantId } = useAuth();
    const [theme, setTheme] = useState("");
    const [status, setStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
    const [docs, setDocs] = useState<Doc[]>([]);
    const [loadingDocs, setLoadingDocs] = useState(true);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

    const fetchDocs = useCallback(async () => {
        if (!tenantId) return;
        const { data, error } = await supabase
            .from("documents")
            .select("document_id, file_url, format, theme, status, created_at")
            .eq("tenant_id", tenantId)
            .order("created_at", { ascending: false });

        if (!error && data) setDocs(data as Doc[]);
    }, [tenantId]);

    useEffect(() => {
        (async () => {
            setLoadingDocs(true);
            await fetchDocs();
            setLoadingDocs(false);
        })();
    }, [fetchDocs]);

    // Stop any in-flight poll if the component unmounts mid-upload.
    useEffect(() => {
        return () => {
            if (pollRef.current) clearInterval(pollRef.current);
        };
    }, []);

    const { getRootProps, getInputProps, isDragActive } = useDropzone({
        accept: { "application/pdf": [".pdf"] },
        disabled: !theme.trim() || status === "uploading",

        onDrop: async (files) => {
            const file = files[0];
            if (!file || !tenantId || !theme.trim()) return;
            setStatus("uploading");
            setErrorMessage(null);

            try {
                const createRes = await authedFetch("/documents", {
                    method: "POST",
                    body: JSON.stringify({
                        tenant_id: tenantId,
                        format: "pdf",
                        file_url: file.name,
                        theme: theme.trim(),
                    }),
                });
                if (!createRes.ok) throw new Error("Failed to create document record");
                const created = await createRes.json();
                const documentId = created.document_id;

                // Show the new row right away (status: 'uploaded'), then poll
                // while the pipeline runs so 'processing' is actually visible
                // instead of being invisibly skipped between one fetch before
                // the upload and one fetch after it.
                await fetchDocs();
                pollRef.current = setInterval(fetchDocs, STATUS_POLL_INTERVAL_MS);

                const formData = new FormData();
                formData.append("document_id", documentId);
                formData.append("tenant_id", tenantId);
                formData.append("file", file);

                const uploadRes = await authedFetch("/kb/upload", {
                    method: "POST",
                    body: formData,
                });
                if (!uploadRes.ok) {
                    let message = "Upload failed. Please try again.";
                    if (uploadRes.status === 400 || uploadRes.status === 422) {
                        try {
                            const errBody = await uploadRes.json();
                            message = errBody.detail ?? errBody.message ?? message;
                        } catch {
                            // response wasn't JSON — fall back to the generic message
                        }
                    }
                    throw new Error(message);
                }

                setStatus("success");
                setTheme("");
            } catch (err) {
                setStatus("error");
                setErrorMessage(err instanceof Error ? err.message : "Something went wrong.");
            } finally {
                // Always stop polling and do one guaranteed final fetch, on
                // both success and failure — previously a failed upload never
                // refetched at all, so a 'failed' row silently didn't appear
                // until the next manual page reload.
                if (pollRef.current) {
                    clearInterval(pollRef.current);
                    pollRef.current = null;
                }
                await fetchDocs();
            }
        },
    });

    if (!tenantId) {
        return <div className="p-8 text-text-secondary">Loading your account...</div>;
    }

    return (
        <>
            {errorMessage && (
                <div className="fixed bottom-4 right-4 max-w-sm rounded-lg bg-status-declinedSoft border border-status-declined/30 backdrop-blur-glass text-text-primary px-4 py-3 shadow-card flex items-start gap-3 z-50">
                    <p className="text-sm">{errorMessage}</p>
                    <button
                        onClick={() => setErrorMessage(null)}
                        className="text-text-secondary hover:text-text-primary text-sm font-bold"
                        aria-label="Dismiss"
                    >
                        ×
                    </button>
                </div>
            )}

            <div className="p-8">
                <h1 className="text-2xl font-semibold text-text-primary mb-6">Documents & FAQs</h1>

                <GlassCard padding="lg" className="mb-6">
                    <select
                        value={theme}
                        onChange={(e) => setTheme(e.target.value)}
                        className="mb-4 w-full rounded-lg border border-white/[0.1] bg-white/[0.05] px-3 py-2.5 text-sm text-text-primary"
                    >
                        <option value="" className="bg-obsidian-surface text-text-primary">
                            Select a category…
                        </option>
                        {CATEGORY_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value} className="bg-obsidian-surface text-text-primary">
                                {opt.label}
                            </option>
                        ))}
                    </select>

                    <div
                        {...getRootProps()}
                        className={`rounded-xl2 border-2 border-dashed p-10 text-center transition-colors ${
                            theme.trim() && status !== "uploading"
                                ? isDragActive
                                    ? "border-accent-violet bg-gradient-brand-soft cursor-pointer"
                                    : "border-white/[0.15] hover:border-white/[0.3] cursor-pointer"
                                : "border-white/[0.08] cursor-not-allowed opacity-50"
                        }`}
                    >
                        <input {...getInputProps()} />
                        <p className="text-sm text-text-secondary">
                            {theme.trim()
                                ? "Drag a PDF here, or click to select"
                                : "Enter a category above before uploading"}
                        </p>
                        {status === "uploading" && (
                            <p className="mt-2 text-sm text-status-pending">Uploading…</p>
                        )}
                        {status === "success" && (
                            <p className="mt-2 text-sm text-status-active">Uploaded ✓</p>
                        )}
                        {status === "error" && (
                            <p className="mt-2 text-sm text-status-declined">Upload failed</p>
                        )}
                    </div>
                </GlassCard>

                <div>
                    <h2 className="text-lg font-medium text-text-primary mb-3">Your documents</h2>

                    <GlassCard padding="none">
                        {loadingDocs && (
                            <div className="p-8 space-y-3">
                                {[...Array(3)].map((_, i) => (
                                    <div key={i} className="h-10 w-full rounded-md bg-white/[0.04] animate-pulse" />
                                ))}
                            </div>
                        )}

                        {!loadingDocs && docs.length === 0 && (
                            <p className="p-12 text-center text-sm text-text-secondary">
                                No documents uploaded yet.
                            </p>
                        )}

                        {!loadingDocs && docs.length > 0 && (
                            <table className="w-full text-left">
                                <thead>
                                    <tr className="border-b border-white/[0.08]">
                                        <th className="px-6 py-4 text-xs font-medium text-text-secondary">Filename</th>
                                        <th className="px-6 py-4 text-xs font-medium text-text-secondary">Category</th>
                                        <th className="px-6 py-4 text-xs font-medium text-text-secondary">Status</th>
                                        <th className="px-6 py-4 text-xs font-medium text-text-secondary">Uploaded</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {docs.map((doc) => (
                                        <tr key={doc.document_id} className="row-alt border-b border-white/[0.04] hover:bg-white/[0.03]">
                                            <td className="px-6 py-4 text-sm text-text-primary">{doc.file_url ?? "Untitled"}</td>
                                            <td className="px-6 py-4 text-sm text-text-secondary">{categoryLabel(doc.theme)}</td>
                                            <td className="px-6 py-4"><StatusPill status={doc.status} /></td>
                                            <td className="px-6 py-4 text-sm text-text-secondary">
                                                {new Date(doc.created_at).toLocaleString()}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        )}
                    </GlassCard>
                </div>
            </div>
        </>
    );
}
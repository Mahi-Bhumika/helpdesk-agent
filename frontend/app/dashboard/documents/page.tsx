"use client"

import { useDropzone } from "react-dropzone";
import { useEffect, useState, useCallback } from "react";
import { useAuth } from "@/lib/auth-context";
import { supabase } from "@/lib/supabase";

type Doc = {
    document_id: string;
    file_url: string | null;
    format: string | null;
    theme: string | null;
    status: string;
    created_at: string;
};

export default function DocumentsPage() {
    const { tenantId } = useAuth();
    const [theme, setTheme] = useState("");
    const [status, setStatus] = useState<"idle" | "uploading" | "success" | "error">("idle");
    const [docs, setDocs] = useState<Doc[]>([]);
    const [loadingDocs, setLoadingDocs] = useState(true);

    const fetchDocs = useCallback(async () => {
        if (!tenantId) return;
        setLoadingDocs(true);
        const { data, error } = await supabase
            .from("documents")
            .select("document_id, file_url, format, theme, status, created_at")
            .eq("tenant_id", tenantId)
            .order("created_at", { ascending: false });

        if (!error && data) setDocs(data as Doc[]);
        setLoadingDocs(false);
    }, [tenantId]);

    useEffect(() => {
        fetchDocs();
    }, [fetchDocs]);

    const { getRootProps, getInputProps } = useDropzone({
        accept: { "application/pdf": [".pdf"] },
        disabled: !theme.trim(), // can't drop a file until a category is entered
        onDrop: async (files) => {
            const file = files[0];
            if (!file || !tenantId || !theme.trim()) return;
            setStatus("uploading");

            try {
                const createRes = await fetch("https://helpdesk-agent-9eu9.onrender.com/documents", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
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

                const formData = new FormData();
                formData.append("document_id", documentId);
                formData.append("tenant_id", tenantId);
                formData.append("file", file);

                const uploadRes = await fetch("https://helpdesk-agent-9eu9.onrender.com/kb/upload", {
                    method: "POST",
                    body: formData,
                });
                if (!uploadRes.ok) throw new Error("Failed to upload file");

                setStatus("success");
                setTheme(""); // reset for the next upload
                await fetchDocs();
            } catch {
                setStatus("error");
            }
        },
    });

    if (!tenantId) {
        return <div>Loading your account...</div>;
    }

    return (
        <div>
            <h1 className="text-xl font-bold mb-4">Documents & FAQs</h1>

            <input
                type="text"
                placeholder="Category (e.g. Billing, Onboarding, Technical)"
                value={theme}
                onChange={(e) => setTheme(e.target.value)}
                className="mb-4 w-full rounded-md border border-gray-300 px-3 py-2"
            />

            <div
                {...getRootProps()}
                className={`border-2 border-dashed p-8 text-center rounded-md ${
                    theme.trim() ? "cursor-pointer" : "cursor-not-allowed opacity-50"
                }`}
            >
                <input {...getInputProps()} />
                <p>
                    {theme.trim()
                        ? "Drag a PDF here, or click to select"
                        : "Enter a category above before uploading"}
                </p>
                {status === "uploading" && <p className="mt-2 text-sm text-gray-400">Uploading…</p>}
                {status === "success" && <p className="mt-2 text-sm text-green-500">Uploaded ✓</p>}
                {status === "error" && <p className="mt-2 text-sm text-red-500">Upload failed</p>}
            </div>

            <div className="mt-8">
                <h2 className="text-lg font-semibold mb-2">Your documents</h2>
                {loadingDocs ? (
                    <p className="text-sm text-gray-400">Loading documents...</p>
                ) : docs.length === 0 ? (
                    <p className="text-sm text-gray-400">No documents uploaded yet.</p>
                ) : (
                    <table className="w-full text-left border-collapse">
                        <thead>
                            <tr className="border-b border-gray-700">
                                <th className="py-2 pr-4">Filename</th>
                                <th className="py-2 pr-4">Category</th>
                                <th className="py-2 pr-4">Status</th>
                                <th className="py-2 pr-4">Uploaded</th>
                            </tr>
                        </thead>
                        <tbody>
                            {docs.map((doc) => (
                                <tr key={doc.document_id} className="border-b border-gray-800">
                                    <td className="py-2 pr-4">{doc.file_url ?? "Untitled"}</td>
                                    <td className="py-2 pr-4">{doc.theme ?? "—"}</td>
                                    <td className="py-2 pr-4">{doc.status}</td>
                                    <td className="py-2 pr-4">
                                        {new Date(doc.created_at).toLocaleString()}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>
        </div>
    );
}
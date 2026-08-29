"use client"

import { useAuth } from "@/lib/auth-context";

export default function EmbedPage() {
    const { tenantId } = useAuth();

    if (!tenantId) {
        return <div>Loading...</div>;
    }

    const snippet = `<script src="https://YOUR-WIDGET-HOST/widget.js" data-tenant-id="${tenantId}"></script>`;

    return (
        <div>
            <h1 className="text-xl font-bold mb-4">Embed Script</h1>
            <p className="text-sm text-gray-400 mb-4">
                Paste this snippet into your website&apos;s HTML, right before the closing{" "}
                <code>&lt;/body&gt;</code> tag.
            </p>
            <pre className="rounded-md border border-gray-700 bg-gray-900 p-4 text-sm overflow-x-auto">
                {snippet}
            </pre>
            <button
                onClick={() => navigator.clipboard.writeText(snippet)}
                className="mt-3 rounded-md bg-black px-4 py-2 text-white hover:bg-gray-800"
            >
                Copy to clipboard
            </button>
        </div>
    );
}
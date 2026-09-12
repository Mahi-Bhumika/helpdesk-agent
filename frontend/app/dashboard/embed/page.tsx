"use client"

import { useAuth } from "@/lib/auth-context";
import { useState, useEffect } from "react";
import { supabase } from "@/lib/supabase";
import { useRouter } from "next/navigation";

type EmbedSettings = {
    tenantId : string;
    apiUrl : string;
    color : string;
    name : string;
    position : string;
    greeting : string;
    cdnUrl : string;
};

function generateEmbedSnippets(settings : EmbedSettings ) {
  
  const { tenantId, name, apiUrl, color, position, greeting, cdnUrl } = settings;

  const html = `<script
  src="${cdnUrl}"
  data-name="${name}"
  data-tenant-id="${tenantId}"
  data-api-url="${apiUrl}"
  data-color="${color}"
  data-position="${position}"
  data-greeting="${greeting}"
  defer
></script>`;

  const nextTsx = `import Script from 'next/script'

// Paste inside your layout.tsx or page.tsx
<Script
  src="${cdnUrl}"
  data-name = "${name}"
  data-tenant-id="${tenantId}"
  data-api-url="${apiUrl}"
  data-color="${color}"
  data-position="${position}"
  data-greeting="${greeting}"
  strategy="lazyOnload"
/>`;

const jsx = `<script
  src="${cdnUrl}"
  data-name = "${name}"
  data-tenant-id="${tenantId}"
  data-api-url="${apiUrl}"
  data-color="${color}"
  data-position="${position}"
  data-greeting="${greeting}"
  defer
/>`;

  return { html, nextTsx, jsx };
}

export default function EmbedPage() {

    const { role, loading : authLoading } = useAuth();
    const router = useRouter();

    useEffect(() => {
      if (!authLoading && role !== "owner") {
        router.push("/dashboard/member");
      }
    }, [authLoading, role, router]);


    const { session }  = useAuth();
    const [format, setFormat] = useState<"html" | "jsx" | "nextTsx">("html");
    const [tenantId, setTenantId] = useState("");
    const [botName, setBotName] = useState("HIKA");
    const [themeColor, setThemeColor] = useState("#1F8A70");
    const [greetingMessage, setGreetingMessage] = useState("Hi! How can I help?");
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!session) return;
        
        const fetchEmbedData = async () => {
            const { data : userRow, error : userError } = await supabase
            .from("users")
            .select("tenant_id")
            .eq("user_id",session.user.id)
            .maybeSingle();

            if (userError || !userRow) {
                console.error("Could not find user's tenant : ", userError);
                setLoading(false);
                return;
            }

            const { data : tenantRow, error : tenantError } = await supabase
            .from("tenants")
            .select("tenant_id, theme_color, bot_name, greeting_message")
            .eq("tenant_id",userRow.tenant_id)
            .maybeSingle()
            
            if (tenantError || !tenantRow){
                console.error("Could not fetch tenant settings : ", tenantError);
                setLoading(false);
                return;
            }
            setTenantId(tenantRow.tenant_id);
            setThemeColor(tenantRow.theme_color || "#2ba98a");
            setBotName(tenantRow.bot_name);
            setGreetingMessage(tenantRow.greeting_message || "Hi! How can I help?");
            setLoading(false);
        };

        fetchEmbedData();
    }, [session]);

    if (loading) return <div> Loading...</div>
    
    const snippets = generateEmbedSnippets({
    tenantId,
    apiUrl: "https://helpdesk-agent-9eu9.onrender.com",
    name : botName,
    color : themeColor,
    position: "bottom-right",
    greeting: greetingMessage,
    cdnUrl: "https://helpdesk-agent-mahi-bhumika.vercel.app/widget.js",
    })

    return (
    <div>
      <h1 className="text-xl font-bold mb-4">Embed Script</h1>
      <p className="text-sm text-gray-400 mb-4">
        Paste this snippet into your website&apos;s HTML, right before the closing{" "}
        <code>&lt;/body&gt;</code> tag.
      </p>

      <div className="flex gap-2 mb-3">
        <button
          onClick={() => setFormat("html")}
          className={format === "html" ? "font-bold underline" : ""}
        >
          HTML
        </button>
        <button
          onClick={() => setFormat("nextTsx")}
          className={format === "nextTsx" ? "font-bold underline" : ""}
        >
          Next.js
        </button>
        <button
          onClick={() => setFormat("jsx")}
          className={format === "jsx" ? "font-bold underline" : ""}
        >
          JSX
        </button>
      </div>

      <pre className="rounded-md border border-gray-700 bg-gray-900 p-4 text-sm overflow-x-auto">
        {snippets[format]}
      </pre>

      <button
        onClick={() => navigator.clipboard.writeText(snippets[format])}
        className="mt-3 rounded-md bg-black px-4 py-2 text-white hover:bg-gray-800"
      >
        Copy to clipboard
      </button>
    </div>
  );
}
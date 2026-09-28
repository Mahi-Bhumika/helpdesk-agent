"use client"

import { useAuth } from "@/lib/auth-context";
import { useState, useEffect } from "react";
import { supabase } from "@/lib/supabase";
import { useRouter } from "next/navigation";
import GlassCard from "@/components/GlassCard";
import Button from "@/components/Button";

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

const FORMAT_LABELS = {
  html: "HTML",
  nextTsx: "Next.js",
  jsx: "JSX",
} as const;

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
    const [copied, setCopied] = useState(false);

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

    if (loading) return <div className="p-8 text-text-secondary">Loading...</div>;
    
    const snippets = generateEmbedSnippets({
    tenantId,
    apiUrl: "https://helpdesk-agent-1.onrender.com",
    name : botName,
    color : themeColor,
    position: "bottom-right",
    greeting: greetingMessage,
    cdnUrl: "https://helpdesk-agent-mahi-bhumika.vercel.app/widget.js",
    })

    function handleCopy() {
      navigator.clipboard.writeText(snippets[format]);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }

    return (
    <div className="p-8">
      <h1 className="text-2xl font-semibold text-text-primary mb-2">Embed Script</h1>
      <p className="text-sm text-text-secondary mb-6">
        Paste this snippet into your website&apos;s HTML, right before the closing{" "}
        <code className="text-text-primary">&lt;/body&gt;</code> tag.
      </p>

      <GlassCard padding="lg">
        <div className="flex gap-2 mb-4">
          {(Object.keys(FORMAT_LABELS) as Array<keyof typeof FORMAT_LABELS>).map((key) => (
            <button
              key={key}
              onClick={() => setFormat(key)}
              className={
                format === key
                  ? "rounded-lg px-3 py-1.5 text-sm font-medium bg-gradient-brand text-white shadow-glow"
                  : "rounded-lg px-3 py-1.5 text-sm font-medium text-text-secondary hover:text-text-primary hover:bg-white/[0.05]"
              }
            >
              {FORMAT_LABELS[key]}
            </button>
          ))}
        </div>

        <pre className="rounded-xl2 border border-white/[0.08] bg-obsidian-surface p-4 text-sm text-text-primary overflow-x-auto font-mono">
          {snippets[format]}
        </pre>

        <Button variant="secondary" onClick={handleCopy} className="mt-4">
          {copied ? "Copied ✓" : "Copy to clipboard"}
        </Button>
      </GlassCard>
    </div>
  );
}
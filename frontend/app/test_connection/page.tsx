"use client"

import { useState } from "react";

interface TenantResponse {
    tenant_id : number;
    company_name : string;
    invite_token : string;
    created_at : string;
}

export default function TestConnection(){
    const [ companyName, setCompanyName ] = useState("");
    const [ typeOfBusiness, setTypeOfBusiness ] = useState("");
    const [ botName, setBotName ] = useState("");
    const [ greetingMessage, setGreetingMessage ] = useState("");

    const [ result, setResult ] = useState<TenantResponse | null>(null);
    const [ loading, setLoading ] = useState(false);
    const [error, setError ] = useState<string | null>(null);

    async function createTenant(e : React.FormEvent){
        e.preventDefault();
        setLoading(true);
        setError(null);
        setResult(null);
    
    try {
        const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/tenants`, {
            method : "POST",
            headers : { "Content-Type" : "application/json" },
            body : JSON.stringify({
                company_name : companyName,
                type_of_business : typeOfBusiness || null,
                subscription_plan : null,
                bot_name : botName || null,
                greeting_message : greetingMessage || null,
                theme_color : null,
            }),
        });

        if (!res.ok){
            const detail = await res.text();
            throw new Error(`Request failed : ${res.status} - ${detail}`);
        }

        const data : TenantResponse = await res.json();
        setResult(data);
    }

    catch(err) {
        setError(err instanceof Error ? err.message : "Something went wrong");
    }

    finally{
        setLoading(false);
    }
}


  return (
    <main style={{ padding: "2rem", fontFamily: "sans-serif", maxWidth: 480 }}>
      <h1>Create Tenant — Backend Connection Test</h1>
      <p style={{ color: "#666" }}>
        POST {process.env.NEXT_PUBLIC_API_URL}/tenants
      </p>

      <form onSubmit={createTenant} style={{ display: "flex", flexDirection: "column", gap: "0.75rem", marginTop: "1rem" }}>
        <label>
          Company name *
          <input
            required
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
            style={{ display: "block", width: "100%", padding: "0.5rem" }}
          />
        </label>

        <label>
          Type of business
          <input
            value={typeOfBusiness}
            onChange={(e) => setTypeOfBusiness(e.target.value)}
            style={{ display: "block", width: "100%", padding: "0.5rem" }}
          />
        </label>

        <label>
          Bot name
          <input
            value={botName}
            onChange={(e) => setBotName(e.target.value)}
            style={{ display: "block", width: "100%", padding: "0.5rem" }}
          />
        </label>

        <label>
          Greeting message
          <input
            value={greetingMessage}
            onChange={(e) => setGreetingMessage(e.target.value)}
            style={{ display: "block", width: "100%", padding: "0.5rem" }}
          />
        </label>

        <button type="submit" disabled={loading} style={{ padding: "0.5rem 1rem", cursor: "pointer" }}>
          {loading ? "Creating..." : "Create Tenant"}
        </button>
      </form>

      {error && <p style={{ color: "red", marginTop: "1rem" }}>Error: {error}</p>}

      {result && (
        <div style={{ marginTop: "1.5rem" }}>
          <p style={{ color: "green" }}> Tenant created </p>
          <pre style={{ background: "#f4f4f4", padding: "1rem", borderRadius: "6px", overflowX: "auto" }}>
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}
    </main>
  );
}
"use client"

import { createContext, useContext, useEffect, useState } from "react";
import { supabase } from "./supabase";
import type { Session } from "@supabase/supabase-js";

type AuthContextType = {
    session: Session | null;
    tenantId: string | null;
    loading: boolean;
};

const AuthContext = createContext<AuthContextType>({
    session: null,
    tenantId: null,
    loading: true,
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [session, setSession] = useState<Session | null>(null);
    const [tenantId, setTenantId] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    async function fetchTenantId(userId: string) {
        const { data, error } = await supabase
            .from("users")
            .select("tenant_id")
            .eq("user_id", userId)
            .single();
        if (!error && data) setTenantId(data.tenant_id);
    }

    useEffect(() => {
        supabase.auth.getSession().then(async ({ data }) => {
            setSession(data.session);
            if (data.session?.user?.id) await fetchTenantId(data.session.user.id);
            setLoading(false);
        });

        const { data: listener } = supabase.auth.onAuthStateChange(async (_event, session) => {
            setSession(session);
            if (session?.user?.id) {
                await fetchTenantId(session.user.id);
            } else {
                setTenantId(null);
            }
        });

        return () => listener.subscription.unsubscribe();
    }, []);

    return (
        <AuthContext.Provider value={{ session, tenantId, loading }}>
            {children}
        </AuthContext.Provider>
    );
}

export const useAuth = () => useContext(AuthContext);
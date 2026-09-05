"use client"

import { createContext, useContext, useEffect, useState, useCallback } from "react";
import { supabase } from "./supabase";
import type { Session } from "@supabase/supabase-js";

type AuthContextType = {
    session: Session | null;
    tenantId: string | null;
    status: string | null;
    role: string | null;
    loading: boolean;
    refetchUserInfo: () => Promise<void>;
};

const AuthContext = createContext<AuthContextType>({
    session: null,
    tenantId: null,
    status: null,
    role: null,
    loading: true,
    refetchUserInfo: async () => {},
});

export function AuthProvider({ children }: { children: React.ReactNode }) {
    const [session, setSession] = useState<Session | null>(null);
    const [tenantId, setTenantId] = useState<string | null>(null);
    const [status, setStatus] = useState<string | null>(null);
    const [role, setRole] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);

    const fetchUserInfo = useCallback(async (userId: string) => {
        const { data, error } = await supabase
            .from("users")
            .select("tenant_id, status, role")
            .eq("user_id", userId)
            .maybeSingle();
        if (!error && data) {
            setTenantId(data.tenant_id);
            setStatus(data.status);
            setRole(data.role);
        } else {
            setTenantId(null);
            setStatus(null);
            setRole(null);
        }
    }, []);

    const refetchUserInfo = useCallback(async () => {
        const { data: { session: currentSession } } = await supabase.auth.getSession();
        if (currentSession?.user?.id) {
            await fetchUserInfo(currentSession.user.id);
        }
    }, [fetchUserInfo]);

    useEffect(() => {
        supabase.auth.getSession().then(async ({ data }) => {
            setSession(data.session);
            if (data.session?.user?.id) await fetchUserInfo(data.session.user.id);
            setLoading(false);
        });

        const { data: listener } = supabase.auth.onAuthStateChange(async (_event, session) => {
            setSession(session);
            if (session?.user?.id) {
                await fetchUserInfo(session.user.id);
            } else {
                setTenantId(null);
                setStatus(null);
                setRole(null);
            }
        });

        return () => listener.subscription.unsubscribe();
    }, [fetchUserInfo]);

    return (
        <AuthContext.Provider value={{ session, tenantId, status, role, loading, refetchUserInfo }}>
            {children}
        </AuthContext.Provider>
    );
}

export const useAuth = () => useContext(AuthContext);
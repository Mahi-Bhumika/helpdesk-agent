"use client"

import { useAuth } from "@/lib/auth-context";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { supabase } from "@/lib/supabase";
import Sidebar from "@/components/sidebar"

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
    const { session, loading, role, status } = useAuth();
    const router = useRouter();
    const [statusChecked, setStatusChecked] = useState(false);

useEffect(() => {
    if (loading) return;
    if (!session) {
        router.push("/login");
        return;
    }
    if (status === "declined") {
        router.push("/declined");
        return;
    }
    if (status !== "active") {
        router.push("/pending");
        return;
    }
    setStatusChecked(true);
}, [loading, session, status, router]);

    if (loading || !statusChecked) {
        return <div className="flex min-h-screen items-center justify-center">Loading...</div>
    }
    if (!session) {
        return null;
    }

    return (
         <div className="flex">
      <Sidebar
        isOwner={role === "owner"}
        footer={
          <button
            onClick={async () => {
              await supabase.auth.signOut();
              router.push("/login");
            }}
            className="text-left text-sm text-gray-400 hover:text-white transition-colors"
          >
            Log out
          </button>
        }
      />
      <main className="flex-1 p-6 bg-[#0B0B0C] min-h-screen">{children}</main>
    </div>
  );
}
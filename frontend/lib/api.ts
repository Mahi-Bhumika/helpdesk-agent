import { supabase } from "./supabase";

const API_BASE = process.env.NEXT_PUBLIC_API_URL!; // your onrender.com URL

export async function authedFetch(path: string, options: RequestInit = {}) {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;

  if (!token) {
    window.location.href = "/login";
    throw new Error("No active session — redirected to login");
  }

  const isFormData = options.body instanceof FormData;

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(options.headers || {}),
      Authorization: `Bearer ${token}`,
      // Don't set Content-Type for FormData — the browser needs to add
      // its own multipart boundary. Only set it for JSON bodies.
      ...(isFormData ? {} : { "Content-Type": "application/json" }),
    },
  });

  if (res.status === 401) {
    window.location.href = "/login";
    throw new Error("Session expired — redirected to login");
  }

  return res;
}
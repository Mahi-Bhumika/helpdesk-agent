"use client";

import { usePathname } from "next/navigation";

export default function HikaWatermark() {
  const pathname = usePathname();

  // Landing page already has this exact branding in its own nav — skip it there.
  if (pathname === "/") return null;

  return (
    <div className="fixed top-6 left-8 z-50 pointer-events-none select-none flex flex-col">
      <span className="text-lg font-medium text-text-primary tracking-tight">HIKA</span>
      <span className="text-[10px] text-text-muted tracking-wide uppercase -mt-0.5">
        Helpdesk Intelligence &amp; Knowledge Automation
      </span>
    </div>
  );
}
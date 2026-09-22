"use client";

import { usePathname } from "next/navigation";

export default function HikaWatermark() {
  const pathname = usePathname();

  if (pathname === "/") return null;

  return (
    <div className="fixed top-6 left-6 z-50 pointer-events-none select-none flex flex-col w-52">
      <span className="text-lg font-medium text-text-primary tracking-tight">HIKA</span>
      <span className="text-[9px] leading-tight text-text-muted tracking-wide uppercase -mt-0.5">
        Helpdesk Intelligence &amp; Knowledge Automation
      </span>
    </div>
  );
}
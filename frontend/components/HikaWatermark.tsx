"use client";

import { usePathname } from "next/navigation";

export default function HikaWatermark() {
  const pathname = usePathname();

  // Landing page already has its own HIKA wordmark in the nav — skip it there.
  if (pathname === "/") return null;

  return (
    <div className="fixed top-4 left-5 z-50 pointer-events-none select-none">
      <span className="text-xs font-medium text-white/40 tracking-wide">HIKA</span>
    </div>
  );
}
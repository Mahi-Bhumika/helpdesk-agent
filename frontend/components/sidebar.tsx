"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { navItems } from "./nav-items";

interface SidebarProps {
  isOwner: boolean;
  footer?: React.ReactNode;
}

export default function Sidebar({ isOwner, footer }: SidebarProps) {
  const pathname = usePathname();
  const visibleItems = navItems.filter((item) => !item.ownerOnly || isOwner);

  return (
    <aside className="flex h-screen w-64 flex-col bg-[#0B0B0C] border-r border-white/10 px-4 py-6">
      <div className="mb-8 px-2">
        <span className="text-lg font-semibold text-white font-[Inter]">HIKA</span>
      </div>

      <nav className="flex flex-col gap-1">
        {visibleItems.map(({ label, href, icon: Icon }) => {
          const isActive =
            href === "/dashboard"
            ? pathname === "/dashboard"
            : pathname === href || pathname?.startsWith(href + "/");
          return (
            <Link
              key={href}
              href={href}
              className={`group flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors
                ${isActive
                  ? "bg-gradient-to-r from-[#4F46E5] to-[#7C3AED] text-white"
                  : "text-gray-400 hover:bg-white/5 hover:text-white"}`}
            >
              <Icon size={18} className={isActive ? "text-white" : "text-gray-500 group-hover:text-white"} />
              {label}
            </Link>
          );
        })}
      </nav>

      {footer && <div className="mt-auto pt-4 border-t border-white/10">{footer}</div>}
    </aside>
  );
}
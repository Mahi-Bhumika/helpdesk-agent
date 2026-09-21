import {
  LayoutDashboard,
  BarChart3,
  FileText,
  MessageSquare,
  Settings,
  Code2,
  UserPlus,
  Users,
} from "lucide-react";

export const navItems = [
  { label: "Overview",     href: "/dashboard",               icon: LayoutDashboard },
  { label: "Analytics",    href: "/dashboard/analytics",      icon: BarChart3 },
  { label: "Documents",    href: "/dashboard/documents",      icon: FileText },
  { label: "Sessions",     href: "/dashboard/sessions",       icon: MessageSquare },
  { label: "Bot Settings", href: "/dashboard/settings",       icon: Settings },
  // owner-only
  { label: "Embed Script", href: "/dashboard/embed", icon: Code2, ownerOnly: true },
  { label: "Invites",      href: "/dashboard/admin/invites",  icon: UserPlus, ownerOnly: true },
  { label: "Members",      href: "/dashboard/member",         icon: Users,    ownerOnly: true },
];
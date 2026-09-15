interface PillBadgeProps {
  status: "active" | "completed" | "pending" | "processing" | "declined" | "failed";
  label?: string;
}

const statusStyles: Record<PillBadgeProps["status"], string> = {
  active:
    "bg-emerald-500/10 text-emerald-400 border-emerald-500/30 shadow-[0_0_8px_rgba(16,185,129,0.4)]",
  completed:
    "bg-blue-500/10 text-blue-400 border-blue-500/30 shadow-[0_0_8px_rgba(59,130,246,0.3)]",
  pending:
    "bg-amber-500/10 text-amber-400 border-amber-500/30 shadow-[0_0_8px_rgba(245,158,11,0.35)]",
  processing:
    "bg-amber-500/10 text-amber-400 border-amber-500/30 shadow-[0_0_8px_rgba(245,158,11,0.35)] animate-pulse",
  declined:
    "bg-red-500/10 text-red-400 border-red-500/30",
  failed:
    "bg-red-500/10 text-red-400 border-red-500/30",
};

const defaultLabels: Record<PillBadgeProps["status"], string> = {
  active: "Active",
  completed: "Completed",
  pending: "Pending",
  processing: "Processing",
  declined: "Declined",
  failed: "Failed",
};

export default function PillBadge({ status, label }: PillBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium font-[Inter] ${statusStyles[status]}`}
    >
      {label ?? defaultLabels[status]}
    </span>
  );
}
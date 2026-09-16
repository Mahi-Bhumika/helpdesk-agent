import { HTMLAttributes, forwardRef } from "react";
import clsx from "clsx";

interface GlassCardProps extends HTMLAttributes<HTMLDivElement> {
  /** Adds the luminous gradient edge — use sparingly, for the one emphasized card on a page */
  glow?: boolean;
  /** Adds a hover state — use for cards that are clickable/interactive */
  interactive?: boolean;
  padding?: "none" | "sm" | "md" | "lg";
}

const paddingMap = {
  none: "",
  sm: "p-4",
  md: "p-6",
  lg: "p-8",
};

/**
 * GlassCard — the base surface for nearly everything in the dashboard:
 * metric cards, table containers, settings panels, empty states.
 *
 * Usage:
 *   <GlassCard padding="lg">...</GlassCard>
 *   <GlassCard glow padding="md">...</GlassCard>          // one emphasized card per page, not every card
 *   <GlassCard interactive onClick={...}>...</GlassCard>  // clickable card (e.g. a document row card)
 */
const GlassCard = forwardRef<HTMLDivElement, GlassCardProps>(
  ({ className, glow, interactive, padding = "md", children, ...props }, ref) => {
    return (
      <div
        ref={ref}
        className={clsx(
          "glass",
          paddingMap[padding],
          interactive && "glass-hover cursor-pointer",
          glow && "glass-glow-border",
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);

GlassCard.displayName = "GlassCard";

export default GlassCard;

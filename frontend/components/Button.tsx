import { ButtonHTMLAttributes, forwardRef } from "react";
import clsx from "clsx";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: "primary" | "secondary" | "ghost" | "danger";
  size?: "sm" | "md";
  loading?: boolean;
}

const base =
  "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed";

const variants: Record<string, string> = {
  primary:
    "bg-gradient-brand text-white shadow-glow hover:brightness-110 active:brightness-95",
  secondary:
    "bg-white/[0.06] text-text-primary border border-white/[0.1] hover:bg-white/[0.1]",
  ghost: "text-text-secondary hover:text-text-primary hover:bg-white/[0.05]",
  danger:
    "bg-status-declined/10 text-status-declined border border-status-declined/30 hover:bg-status-declined/20",
};

const sizes: Record<string, string> = {
  sm: "text-sm px-3 py-1.5",
  md: "text-sm px-4 py-2.5",
};

/**
 * Usage:
 *   <Button>Save changes</Button>
 *   <Button variant="secondary">Copy link</Button>
 *   <Button variant="danger">Delete document</Button>
 *   <Button loading>Uploading...</Button>
 *
 * Copy is a verb describing exactly what happens on click — keep new usages consistent
 * with that (e.g. "Approve", "Decline", "Delete document", not "Submit"/"OK").
 */
const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = "primary", size = "md", loading, children, disabled, ...props }, ref) => {
    return (
      <button
        ref={ref}
        disabled={disabled || loading}
        className={clsx(base, variants[variant], sizes[size], className)}
        {...props}
      >
        {loading && (
          <span className="h-3.5 w-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" />
        )}
        {children}
      </button>
    );
  }
);

Button.displayName = "Button";

export default Button;

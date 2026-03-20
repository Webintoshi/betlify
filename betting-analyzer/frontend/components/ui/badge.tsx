import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type BadgeVariant = "neutral" | "success" | "warning" | "error" | "accent" | "outline";
type BadgeSize = "sm" | "md";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  size?: BadgeSize;
  dot?: boolean;
}

const variantStyles: Record<BadgeVariant, string> = {
  neutral: [
    "bg-sky-500/10",
    "text-sky-300",
    "border border-sky-500/20"
  ].join(" "),
  
  accent: [
    "bg-accent/20",
    "text-accent",
    "border border-accent/40",
    "shadow-[0_0_12px_rgba(14,165,233,0.2)]"
  ].join(" "),
  
  success: [
    "bg-success/20",
    "text-success-bright",
    "border border-success/30",
    "shadow-[0_0_12px_rgba(16,185,129,0.2)]"
  ].join(" "),
  
  warning: [
    "bg-warning/20",
    "text-warning-bright",
    "border border-warning/30",
    "shadow-[0_0_12px_rgba(245,158,11,0.2)]"
  ].join(" "),
  
  error: [
    "bg-error/20",
    "text-error-bright",
    "border border-error/30",
    "shadow-[0_0_12px_rgba(239,68,68,0.2)]"
  ].join(" "),
  
  outline: [
    "bg-transparent",
    "text-foreground-tertiary",
    "border border-sky-500/30"
  ].join(" ")
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: "px-2 py-0.5 text-[10px]",
  md: "px-2.5 py-1 text-xs"
};

const dotColors: Record<BadgeVariant, string> = {
  neutral: "bg-sky-400",
  accent: "bg-accent",
  success: "bg-success-bright",
  warning: "bg-warning-bright",
  error: "bg-error-bright",
  outline: "bg-sky-400"
};

export function Badge({ 
  className, 
  variant = "neutral", 
  size = "md",
  dot = false,
  children,
  ...props 
}: BadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5",
        "font-medium",
        "rounded-full",
        "transition-all duration-200",
        sizeStyles[size],
        variantStyles[variant],
        className
      )}
      {...props}
    >
      {dot && (
        <span 
          className={cn(
            "w-1.5 h-1.5 rounded-full",
            dotColors[variant]
          )} 
        />
      )}
      {children}
    </span>
  );
}

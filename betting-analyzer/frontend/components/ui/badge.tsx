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
    "bg-white/[0.06]",
    "text-foreground-secondary",
    "border border-white/[0.08]"
  ].join(" "),
  
  accent: [
    "bg-accent/15",
    "text-accent",
    "border border-accent/25"
  ].join(" "),
  
  success: [
    "bg-success/15",
    "text-success",
    "border border-success/25",
    "shadow-[0_0_12px_rgba(16,185,129,0.15)]"
  ].join(" "),
  
  warning: [
    "bg-warning/15",
    "text-warning",
    "border border-warning/25",
    "shadow-[0_0_12px_rgba(245,158,11,0.15)]"
  ].join(" "),
  
  error: [
    "bg-error/15",
    "text-error",
    "border border-error/25",
    "shadow-[0_0_12px_rgba(244,63,94,0.15)]"
  ].join(" "),
  
  outline: [
    "bg-transparent",
    "text-foreground-tertiary",
    "border border-white/[0.15]"
  ].join(" ")
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: "px-2 py-0.5 text-[10px]",
  md: "px-2.5 py-1 text-xs"
};

const dotColors: Record<BadgeVariant, string> = {
  neutral: "bg-foreground-muted",
  accent: "bg-accent",
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-error",
  outline: "bg-foreground-muted"
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

import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type BadgeVariant = "neutral" | "success" | "warning" | "error" | "accent";
type BadgeSize = "sm" | "md";

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  size?: BadgeSize;
  dot?: boolean;
}

const variantStyles: Record<BadgeVariant, string> = {
  neutral: [
    "bg-card-hover",
    "text-foreground-tertiary",
    "border border-card-border"
  ].join(" "),
  
  accent: [
    "bg-accent/20",
    "text-accent",
    "border border-accent"
  ].join(" "),
  
  success: [
    "bg-success/20",
    "text-success-bright",
    "border border-success"
  ].join(" "),
  
  warning: [
    "bg-warning/20",
    "text-warning-bright",
    "border border-warning"
  ].join(" "),
  
  error: [
    "bg-error/20",
    "text-error-bright",
    "border border-error"
  ].join(" ")
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: "px-2 py-0.5 text-[10px]",
  md: "px-2.5 py-1 text-xs"
};

const dotColors: Record<BadgeVariant, string> = {
  neutral: "bg-foreground-muted",
  accent: "bg-accent",
  success: "bg-success-bright",
  warning: "bg-warning-bright",
  error: "bg-error-bright"
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
        "font-bold uppercase tracking-wider",
        "rounded-md",
        "transition-colors duration-150",
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

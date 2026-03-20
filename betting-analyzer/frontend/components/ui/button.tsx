"use client";

import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type ButtonVariant = "default" | "secondary" | "ghost" | "danger" | "outline" | "gradient";
type ButtonSize = "sm" | "md" | "lg";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  isLoading?: boolean;
};

const variantStyles: Record<ButtonVariant, string> = {
  default: [
    "bg-accent",
    "text-white",
    "border border-accent",
    "hover:bg-accent/90",
    "hover:shadow-glow",
    "hover:border-accent-secondary",
    "active:scale-[0.98]"
  ].join(" "),
  
  gradient: [
    "bg-gradient-to-r from-accent to-cyan",
    "text-white",
    "border-0",
    "hover:shadow-glow-cyan",
    "hover:opacity-95",
    "active:scale-[0.98]"
  ].join(" "),
  
  secondary: [
    "bg-sky-500/10",
    "text-sky-300",
    "border border-sky-500/20",
    "hover:bg-sky-500/20",
    "hover:border-sky-500/30",
    "active:scale-[0.98]"
  ].join(" "),
  
  outline: [
    "bg-transparent",
    "text-sky-300",
    "border border-sky-500/30",
    "hover:bg-sky-500/10",
    "hover:border-accent/50",
    "active:scale-[0.98]"
  ].join(" "),
  
  ghost: [
    "bg-transparent",
    "text-foreground-tertiary",
    "border border-transparent",
    "hover:bg-sky-500/10",
    "hover:text-sky-300",
    "active:scale-[0.98]"
  ].join(" "),
  
  danger: [
    "bg-error",
    "text-white",
    "border border-error",
    "hover:bg-error/90",
    "hover:shadow-lg hover:shadow-error/20",
    "active:scale-[0.98]"
  ].join(" ")
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "h-8 px-3 text-xs rounded-lg",
  md: "h-10 px-4 text-sm rounded-xl",
  lg: "h-12 px-6 text-sm rounded-xl"
};

export function Button({ 
  className, 
  variant = "default", 
  size = "md",
  isLoading = false,
  disabled,
  children,
  ...props 
}: ButtonProps) {
  return (
    <button
      className={cn(
        "inline-flex items-center justify-center",
        "font-medium",
        "transition-all duration-200 ease-premium",
        "focus:outline-none focus:ring-2 focus:ring-accent/50 focus:ring-offset-2 focus:ring-offset-background",
        "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:shadow-none disabled:active:scale-100",
        sizeStyles[size],
        variantStyles[variant],
        className
      )}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <>
          <svg 
            className="animate-spin -ml-1 mr-2 h-4 w-4 text-current" 
            fill="none" 
            viewBox="0 0 24 24"
          >
            <circle 
              className="opacity-25" 
              cx="12" cy="12" r="10" 
              stroke="currentColor" 
              strokeWidth="4" 
            />
            <path 
              className="opacity-75" 
              fill="currentColor" 
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" 
            />
          </svg>
          {children}
        </>
      ) : children}
    </button>
  );
}

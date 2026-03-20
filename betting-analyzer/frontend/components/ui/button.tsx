"use client";

import type { ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type ButtonVariant = "default" | "secondary" | "ghost" | "danger" | "outline";
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
    "border-2 border-accent",
    "hover:bg-accent/90",
    "hover:border-accent-secondary",
    "active:translate-y-[1px]",
    "shadow-accent"
  ].join(" "),
  
  secondary: [
    "bg-card-hover",
    "text-foreground-secondary",
    "border-2 border-card-border",
    "hover:border-accent/50",
    "hover:text-accent",
    "active:translate-y-[1px]"
  ].join(" "),
  
  outline: [
    "bg-transparent",
    "text-accent",
    "border-2 border-accent",
    "hover:bg-accent/10",
    "active:translate-y-[1px]"
  ].join(" "),
  
  ghost: [
    "bg-transparent",
    "text-foreground-tertiary",
    "border-2 border-transparent",
    "hover:text-accent",
    "hover:bg-card",
    "active:translate-y-[1px]"
  ].join(" "),
  
  danger: [
    "bg-error",
    "text-white",
    "border-2 border-error",
    "hover:bg-error/90",
    "active:translate-y-[1px]",
    "shadow-success"
  ].join(" ")
};

const sizeStyles: Record<ButtonSize, string> = {
  sm: "h-8 px-4 text-xs rounded-md",
  md: "h-10 px-5 text-sm rounded-lg",
  lg: "h-12 px-6 text-sm rounded-lg"
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
        "font-bold uppercase tracking-wide",
        "transition-all duration-150",
        "focus:outline-none focus:ring-2 focus:ring-accent/50 focus:ring-offset-2 focus:ring-offset-background",
        "disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:shadow-none disabled:active:translate-y-0",
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

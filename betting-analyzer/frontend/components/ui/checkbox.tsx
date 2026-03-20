"use client";

import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type CheckboxVariant = "default" | "accent" | "success";

interface CheckboxProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "type"> {
  variant?: CheckboxVariant;
  label?: string;
  error?: boolean;
}

const variantStyles: Record<CheckboxVariant, string> = {
  default: [
    "border-white/20",
    "checked:bg-accent",
    "checked:border-accent",
    "focus:ring-accent/50"
  ].join(" "),
  
  accent: [
    "border-accent/40",
    "checked:bg-accent",
    "checked:border-accent",
    "focus:ring-accent/50"
  ].join(" "),
  
  success: [
    "border-success/40",
    "checked:bg-success",
    "checked:border-success",
    "focus:ring-success/50"
  ].join(" ")
};

export function Checkbox({ 
  className, 
  variant = "default",
  label,
  error,
  id,
  ...props 
}: CheckboxProps) {
  const checkboxId = id || `checkbox-${Math.random().toString(36).substr(2, 9)}`;
  
  return (
    <label 
      htmlFor={checkboxId}
      className={cn(
        "inline-flex items-center gap-3 cursor-pointer group",
        props.disabled && "cursor-not-allowed opacity-50"
      )}
    >
      <div className="relative">
        <input
          id={checkboxId}
          type="checkbox"
          className={cn(
            "peer h-5 w-5 rounded-md appearance-none",
            "bg-white/[0.04]",
            "border-2",
            "transition-all duration-200 ease-premium",
            "focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-background",
            "disabled:cursor-not-allowed",
            "checked:bg-[length:14px_14px]",
            variantStyles[variant],
            error && "border-error focus:ring-error/50",
            className
          )}
          style={{
            backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpolyline points='20 6 9 17 4 12'%3E%3C/polyline%3E%3C/svg%3E")`,
            backgroundRepeat: "no-repeat",
            backgroundPosition: "center"
          }}
          {...props}
        />
        {/* Hover effect overlay */}
        <div className={cn(
          "absolute inset-0 rounded-md",
          "bg-accent/10 opacity-0 group-hover:opacity-100",
          "transition-opacity duration-200",
          "pointer-events-none",
          props.disabled && "hidden"
        )} />
      </div>
      {label && (
        <span className={cn(
          "text-sm text-foreground-secondary select-none",
          "group-hover:text-foreground-primary transition-colors duration-200",
          props.disabled && "text-foreground-muted"
        )}>
          {label}
        </span>
      )}
    </label>
  );
}

// Checkbox Group component for multiple checkboxes
interface CheckboxGroupProps {
  children: React.ReactNode;
  className?: string;
  direction?: "horizontal" | "vertical";
}

export function CheckboxGroup({ 
  children, 
  className,
  direction = "vertical"
}: CheckboxGroupProps) {
  return (
    <div 
      className={cn(
        "flex",
        direction === "vertical" && "flex-col gap-3",
        direction === "horizontal" && "flex-row flex-wrap gap-4",
        className
      )}
    >
      {children}
    </div>
  );
}

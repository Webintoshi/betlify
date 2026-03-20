import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "elevated" | "accent" | "outline";
  hover?: boolean;
}

export function Card({ 
  className, 
  variant = "default", 
  hover = false,
  ...props 
}: CardProps) {
  const variantStyles = {
    default: "bg-card border border-card-border shadow-card",
    elevated: "bg-card-hover border border-card-border shadow-card-hover",
    accent: "bg-card border-2 border-accent shadow-accent",
    outline: "bg-transparent border-2 border-card-border"
  };

  return (
    <div
      className={cn(
        "rounded-xl p-5",
        "transition-all duration-200 ease-premium",
        variantStyles[variant],
        hover && "hover:shadow-card-hover hover:border-accent/30",
        className
      )}
      {...props}
    />
  );
}

interface CardTitleProps extends HTMLAttributes<HTMLHeadingElement> {
  as?: "h1" | "h2" | "h3" | "h4" | "h5" | "h6";
}

export function CardTitle({ 
  className, 
  as: Component = "h3", 
  ...props 
}: CardTitleProps) {
  return (
    <Component 
      className={cn(
        "text-sm font-bold text-foreground-primary tracking-tight uppercase",
        className
      )} 
      {...props} 
    />
  );
}

interface CardDescriptionProps extends HTMLAttributes<HTMLParagraphElement> {}

export function CardDescription({ className, ...props }: CardDescriptionProps) {
  return (
    <p 
      className={cn(
        "text-xs text-foreground-tertiary font-medium",
        className
      )} 
      {...props} 
    />
  );
}

interface CardHeaderProps extends HTMLAttributes<HTMLDivElement> {}

export function CardHeader({ className, ...props }: CardHeaderProps) {
  return (
    <div 
      className={cn(
        "flex flex-col space-y-1.5 pb-4 border-b border-card-border",
        className
      )} 
      {...props} 
    />
  );
}

interface CardContentProps extends HTMLAttributes<HTMLDivElement> {}

export function CardContent({ className, ...props }: CardContentProps) {
  return <div className={cn("pt-4", className)} {...props} />;
}

interface CardFooterProps extends HTMLAttributes<HTMLDivElement> {}

export function CardFooter({ className, ...props }: CardFooterProps) {
  return (
    <div 
      className={cn(
        "flex items-center pt-4 mt-4",
        "border-t border-card-border",
        className
      )} 
      {...props} 
    />
  );
}

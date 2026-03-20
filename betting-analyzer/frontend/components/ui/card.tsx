import type { HTMLAttributes } from "react";
import { cn } from "@/lib/utils";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "glass" | "elevated" | "gradient";
  hover?: boolean;
}

export function Card({ 
  className, 
  variant = "default", 
  hover = false,
  ...props 
}: CardProps) {
  const variants = {
    default: [
      "bg-card/90",
      "border border-white/[0.06]",
      "shadow-card",
      "backdrop-blur-xl"
    ],
    glass: [
      "bg-white/[0.03]",
      "border border-white/[0.08]",
      "shadow-lg",
      "backdrop-blur-2xl"
    ],
    elevated: [
      "bg-card",
      "border border-white/[0.06]",
      "shadow-xl",
      "backdrop-blur-xl"
    ],
    gradient: [
      "bg-gradient-to-br from-card to-card/50",
      "border border-accent/20",
      "shadow-glow-sm",
      "backdrop-blur-xl"
    ]
  };

  return (
    <div
      className={cn(
        "rounded-2xl p-5",
        "transition-all duration-300 ease-premium",
        variants[variant],
        hover && "hover:shadow-card-hover hover:-translate-y-0.5 cursor-pointer",
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
        "text-sm font-semibold text-foreground-primary tracking-tight",
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
        "text-xs text-foreground-tertiary leading-relaxed",
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
        "flex flex-col space-y-1.5 pb-4",
        className
      )} 
      {...props} 
    />
  );
}

interface CardContentProps extends HTMLAttributes<HTMLDivElement> {}

export function CardContent({ className, ...props }: CardContentProps) {
  return <div className={cn("pt-0", className)} {...props} />;
}

interface CardFooterProps extends HTMLAttributes<HTMLDivElement> {}

export function CardFooter({ className, ...props }: CardFooterProps) {
  return (
    <div 
      className={cn(
        "flex items-center pt-4 mt-4",
        "border-t border-white/[0.04]",
        className
      )} 
      {...props} 
    />
  );
}

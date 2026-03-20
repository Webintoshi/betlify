import { cn } from "@/lib/utils";

type ProgressVariant = "default" | "success" | "warning" | "error";

interface ProgressProps {
  value: number;
  max?: number;
  variant?: ProgressVariant;
  size?: "sm" | "md" | "lg";
  className?: string;
  showValue?: boolean;
}

const variantStyles: Record<ProgressVariant, string> = {
  default: "bg-accent",
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-error"
};

const sizeStyles = {
  sm: "h-1.5",
  md: "h-2.5",
  lg: "h-3.5"
};

export function Progress({ 
  value, 
  max = 100,
  variant = "default",
  size = "md",
  className,
  showValue = false
}: ProgressProps) {
  const percentage = Math.max(0, Math.min(100, (value / max) * 100));
  
  return (
    <div className={cn("w-full", className)}>
      <div 
        className={cn(
          "w-full overflow-hidden rounded-sm",
          "bg-card-hover border border-card-border",
          sizeStyles[size]
        )}
      >
        <div
          className={cn(
            "h-full transition-all duration-500 ease-out",
            variantStyles[variant]
          )}
          style={{ width: `${percentage}%` }}
        />
      </div>
      {showValue && (
        <div className="flex justify-between mt-1.5">
          <span className="text-xs text-foreground-muted font-medium">0%</span>
          <span className="text-xs font-bold text-foreground-secondary">
            {percentage.toFixed(0)}%
          </span>
        </div>
      )}
    </div>
  );
}

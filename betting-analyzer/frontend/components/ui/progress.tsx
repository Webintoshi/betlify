import { cn } from "@/lib/utils";

type ProgressVariant = "default" | "success" | "warning" | "error" | "gradient";

interface ProgressProps {
  value: number;
  max?: number;
  variant?: ProgressVariant;
  size?: "sm" | "md" | "lg";
  className?: string;
  barClassName?: string;
  showValue?: boolean;
  animated?: boolean;
}

const variantStyles: Record<ProgressVariant, string> = {
  default: "bg-accent",
  success: "bg-success shadow-[0_0_10px_rgba(16,185,129,0.4)]",
  warning: "bg-warning shadow-[0_0_10px_rgba(245,158,11,0.4)]",
  error: "bg-error shadow-[0_0_10px_rgba(244,63,94,0.4)]",
  gradient: "bg-gradient-to-r from-accent to-accent-secondary"
};

const sizeStyles = {
  sm: "h-1.5",
  md: "h-2",
  lg: "h-3"
};

export function Progress({ 
  value, 
  max = 100,
  variant = "default",
  size = "md",
  className,
  barClassName,
  showValue = false,
  animated = true
}: ProgressProps) {
  const percentage = Math.max(0, Math.min(100, (value / max) * 100));
  
  return (
    <div className={cn("w-full", className)}>
      <div 
        className={cn(
          "w-full overflow-hidden rounded-full",
          "bg-white/[0.06]",
          sizeStyles[size]
        )}
      >
        <div
          className={cn(
            "h-full rounded-full transition-all duration-700 ease-premium",
            variantStyles[variant],
            animated && percentage > 0 && "animate-pulse-subtle",
            barClassName
          )}
          style={{ width: `${percentage}%` }}
        >
          {/* Shimmer effect */}
          {animated && percentage > 0 && (
            <div 
              className="h-full w-full opacity-30"
              style={{
                background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.3), transparent)",
                backgroundSize: "200% 100%",
                animation: "shimmer 2s infinite"
              }}
            />
          )}
        </div>
      </div>
      {showValue && (
        <div className="flex justify-between mt-1.5">
          <span className="text-xs text-foreground-muted">0%</span>
          <span className="text-xs font-medium text-foreground-secondary">
            {percentage.toFixed(0)}%
          </span>
        </div>
      )}
    </div>
  );
}

// Circular Progress for special use cases
interface CircularProgressProps {
  value: number;
  max?: number;
  size?: number;
  strokeWidth?: number;
  variant?: ProgressVariant;
  className?: string;
  children?: React.ReactNode;
}

export function CircularProgress({
  value,
  max = 100,
  size = 64,
  strokeWidth = 4,
  variant = "default",
  className,
  children
}: CircularProgressProps) {
  const percentage = Math.max(0, Math.min(100, (value / max) * 100));
  const radius = (size - strokeWidth) / 2;
  const circumference = radius * 2 * Math.PI;
  const offset = circumference - (percentage / 100) * circumference;
  
  const variantColors: Record<ProgressVariant, string> = {
    default: "#6366f1",
    success: "#10b981",
    warning: "#f59e0b",
    error: "#f43f5e",
    gradient: "url(#gradient)"
  };

  return (
    <div className={cn("relative inline-flex items-center justify-center", className)}>
      <svg width={size} height={size} className="-rotate-90">
        <defs>
          <linearGradient id="gradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#6366f1" />
            <stop offset="100%" stopColor="#8b5cf6" />
          </linearGradient>
        </defs>
        {/* Background circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="rgba(255,255,255,0.06)"
          strokeWidth={strokeWidth}
        />
        {/* Progress circle */}
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={variantColors[variant]}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-700 ease-premium"
        />
      </svg>
      {children && (
        <div className="absolute inset-0 flex items-center justify-center">
          {children}
        </div>
      )}
    </div>
  );
}

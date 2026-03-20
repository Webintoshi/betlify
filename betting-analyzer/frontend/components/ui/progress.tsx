import { cn } from "@/lib/utils";

type ProgressProps = {
  value: number;
  className?: string;
  barClassName?: string;
};

export function Progress({ value, className, barClassName }: ProgressProps) {
  const safe = Math.max(0, Math.min(100, value));
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-[#2a2a3b]", className)}>
      <div
        className={cn("h-full rounded-full bg-[#6366f1] transition-all", barClassName)}
        style={{ width: `${safe}%` }}
      />
    </div>
  );
}

"use client";

import type { InputHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

type CheckboxProps = Omit<InputHTMLAttributes<HTMLInputElement>, "type">;

export function Checkbox({ className, ...props }: CheckboxProps) {
  return (
    <input
      type="checkbox"
      className={cn(
        "h-4 w-4 rounded border border-zinc-500 bg-[#141420] text-[#6366f1] focus:ring-2 focus:ring-[#6366f1]",
        className
      )}
      {...props}
    />
  );
}

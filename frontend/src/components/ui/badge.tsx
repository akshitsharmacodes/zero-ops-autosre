import * as React from "react"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "@/lib/utils"

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2 py-0.5 text-xs font-medium transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default:
          "border-transparent bg-zinc-800 text-zinc-100 shadow",
        secondary:
          "border-transparent bg-zinc-800/80 text-zinc-300",
        destructive:
          "border-red-500/30 bg-red-500/10 text-red-400",
        outline: "text-zinc-300 border-zinc-700",
        success: "border-emerald-500/30 bg-emerald-500/10 text-emerald-400 font-semibold",
        warning: "border-amber-500/30 bg-amber-500/10 text-amber-400 font-semibold",
        info: "border-blue-500/30 bg-blue-500/10 text-blue-400 font-semibold",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return (
    <div className={cn(badgeVariants({ variant }), className)} {...props} />
  )
}

export { Badge, badgeVariants }

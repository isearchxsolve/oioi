import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cn } from "@/lib/utils";

const buttonVariants = {
  default: "bg-brand-500 text-white shadow-glow hover:bg-brand-400 hover:shadow-[0_0_25px_rgba(139,92,246,0.6)] border border-white/20 transition-all duration-300",
  destructive:
    "bg-red-500/20 text-red-400 border border-red-500/30 hover:bg-red-500/30 transition-all duration-300",
  outline: "glass-button",
  secondary:
    "bg-white/10 text-white hover:bg-white/15 backdrop-blur-md border border-white/10 transition-all duration-300",
  ghost: "hover:bg-white/10 hover:text-white transition-all duration-300",
  link: "underline-offset-4 hover:underline text-brand-400 transition-all duration-300",
};

const buttonSizeVariants = {
  default: "h-10 px-4 py-2",
  sm: "h-9 rounded-md px-3",
  lg: "h-12 rounded-lg px-8 text-lg font-medium",
  icon: "h-10 w-10",
};

export const buttonVariantsMap = buttonVariants;

interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: keyof typeof buttonVariants;
  size?: keyof typeof buttonSizeVariants;
  asChild?: boolean;
}

export const Button = React.forwardRef<
  HTMLButtonElement,
  ButtonProps
>(({ className, variant = "default", size = "default", asChild = false, ...props }, ref) => {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      className={cn(
        "inline-flex items-center justify-center rounded-md font-medium ring-offset-background transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-400 focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50",
        buttonVariants[variant],
        buttonSizeVariants[size],
        className
      )}
      ref={ref}
      {...props}
    />
  );
});
Button.displayName = "Button";
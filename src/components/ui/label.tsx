import * as React from "react";

export const Label = React.forwardRef<
  HTMLLabelElement,
  React.LabelHTMLAttributes<HTMLLabelElement>
>(({ className, ...props }, ref) => (
  <label
    className={
      "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70" +
        (className ? ` ${className}` : "")
    }
    ref={ref}
    {...props}
  />
));
Label.displayName = "Label";
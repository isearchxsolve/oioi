import * as React from "react";
import { Toaster as SonnerToaster, toast as sonnerToast } from "sonner";

const Toaster = ({ position = "top-right", ...props }: React.ComponentProps<typeof SonnerToaster>) => (
  <SonnerToaster
    position={position}
    theme="dark"
    className="toaster-group"
    toastOptions={{
      classNames: {
        toast: "bg-slate-900 border border-slate-700 text-slate-100",
        description: "text-slate-400",
        actionButton: "bg-indigo-600 hover:bg-indigo-500",
        cancelButton: "bg-slate-800 hover:bg-slate-700",
        closeButton: "text-slate-400 hover:text-slate-200",
        title: "text-slate-100",
      },
    }}
    {...props}
  />
);

const toast = sonnerToast;

export { Toaster, toast };
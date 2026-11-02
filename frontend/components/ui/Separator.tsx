"use client";

import { forwardRef } from "react";
import { classNames } from "@/lib/utils";

interface SeparatorProps extends React.HTMLAttributes<HTMLHRElement> {
  orientation?: "horizontal" | "vertical";
  decorative?: boolean;
}

export const Separator = forwardRef<HTMLHRElement, SeparatorProps>(
  ({ className, orientation = "horizontal", decorative = true, ...props }, ref) => {
    return (
      <hr
        ref={ref}
        className={classNames(
          "bg-line border-0",
          orientation === "horizontal" ? "w-full h-px" : "h-full w-px",
          props.className,
        )}
        role={decorative ? "none" : "separator"}
        aria-orientation={orientation}
        {...props}
      />
    );
  },
);
Separator.displayName = "Separator";
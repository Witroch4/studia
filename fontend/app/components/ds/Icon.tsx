"use client";

import React from "react";

export interface IconProps extends React.HTMLAttributes<HTMLSpanElement> {
  name: string;
  size?: number | string;
  filled?: boolean;
  weight?: number;
  color?: string;
}

/**
 * Icon — renders a Material Symbols Outlined glyph by ligature name.
 * The icon font is loaded in layout.tsx. Color is inherited by default.
 */
export function Icon({
  name,
  size = 20,
  filled = false,
  weight = 400,
  color,
  className = "",
  style = {},
  ...rest
}: IconProps) {
  return (
    <span
      className={`material-symbols-outlined ${className}`}
      style={{
        fontSize: typeof size === "number" ? `${size}px` : size,
        color: color || "inherit",
        fontVariationSettings: `'FILL' ${filled ? 1 : 0}, 'wght' ${weight}, 'GRAD' 0, 'opsz' ${typeof size === "number" ? size : 24}`,
        lineHeight: 1,
        flexShrink: 0,
        userSelect: "none",
        ...style,
      }}
      {...rest}
    >
      {name}
    </span>
  );
}

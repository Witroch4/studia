"use client";

import React from "react";

export interface AvatarProps {
  initials?: string;
  src?: string;
  size?: number;
  ring?: boolean;
  style?: React.CSSProperties;
}

/**
 * Avatar — circular initials chip with the signature cyan→violet gradient ring.
 * Pass `src` for an image, otherwise `initials` render on a charcoal core.
 */
export function Avatar({ initials = "EJ", src, size = 32, ring = true, style = {} }: AvatarProps) {
  const ringPad = size >= 40 ? 2 : 1;
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: "var(--radius-full)",
        padding: ring ? `${ringPad}px` : 0,
        background: ring ? "linear-gradient(to top right, var(--color-primary), var(--color-secondary))" : "transparent",
        flexShrink: 0,
        ...style,
      }}
    >
      <div
        style={{
          width: "100%",
          height: "100%",
          borderRadius: "var(--radius-full)",
          background: "var(--surface-card)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          overflow: "hidden",
        }}
      >
        {src ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={src} alt={initials} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
        ) : (
          <span
            style={{
              fontFamily: "var(--font-sans)",
              fontWeight: 700,
              fontSize: `${Math.max(10, size * 0.34)}px`,
              color: "var(--text-strong)",
            }}
          >
            {initials}
          </span>
        )}
      </div>
    </div>
  );
}

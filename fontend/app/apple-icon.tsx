import { ImageResponse } from "next/og";

export const size = { width: 180, height: 180 };
export const contentType = "image/png";

/** Apple touch icon — capelo branco sobre gradiente da marca. */
export default function AppleIcon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          backgroundColor: "#06b6d4",
          backgroundImage: "linear-gradient(135deg, #22d3ee 0%, #06b6d4 55%, #8b5cf6 100%)",
        }}
      >
        <svg width="120" height="120" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M24 13 41 20 24 27 7 20Z" fill="#ffffff" />
          <path
            d="M17 23.4 24 26.3 31 23.4V28.6C31 30.9 27.9 32.6 24 32.6 20.1 32.6 17 30.9 17 28.6Z"
            fill="#ffffff"
            fillOpacity="0.92"
          />
          <path d="M40.4 20V30.5" stroke="#ffffff" strokeWidth="1.6" strokeLinecap="round" />
          <circle cx="40.4" cy="32.4" r="2.1" fill="#ffffff" />
        </svg>
      </div>
    ),
    { ...size },
  );
}

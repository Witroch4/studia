import { ImageResponse } from "next/og";

export const alt = "studIA — Estude para concursos com Inteligência Artificial";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

/** Marca (capelo em badge) embutida como data-URI para o satori renderizar. */
const MARK = `data:image/svg+xml,${encodeURIComponent(
  `<svg width="160" height="160" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg"><defs><linearGradient id="g" x1="6" y1="4" x2="42" y2="44" gradientUnits="userSpaceOnUse"><stop stop-color="#22d3ee"/><stop offset="0.55" stop-color="#06b6d4"/><stop offset="1" stop-color="#8b5cf6"/></linearGradient></defs><rect x="2" y="2" width="44" height="44" rx="12" fill="url(#g)"/><path d="M24 13 41 20 24 27 7 20Z" fill="#fff"/><path d="M17 23.4 24 26.3 31 23.4V28.6C31 30.9 27.9 32.6 24 32.6 20.1 32.6 17 30.9 17 28.6Z" fill="#fff" fill-opacity="0.92"/><path d="M40.4 20V30.5" stroke="#fff" stroke-width="1.6" stroke-linecap="round"/><circle cx="40.4" cy="32.4" r="2.1" fill="#fff"/></svg>`,
)}`;

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px",
          backgroundColor: "#0a0a0c",
          backgroundImage:
            "radial-gradient(1100px 520px at 18% -10%, rgba(6,182,212,0.28), transparent 60%), radial-gradient(900px 520px at 105% 120%, rgba(139,92,246,0.26), transparent 55%)",
          color: "#ffffff",
          fontFamily: "sans-serif",
        }}
      >
        {/* topo: marca */}
        <div style={{ display: "flex", alignItems: "center", gap: "22px" }}>
          <img src={MARK} width={96} height={96} alt="" />
          <div style={{ display: "flex", fontSize: 58, fontWeight: 700, letterSpacing: "-2px" }}>
            <span>stud</span>
            <span style={{ color: "#22d3ee" }}>IA</span>
          </div>
        </div>

        {/* meio: headline */}
        <div style={{ display: "flex", flexDirection: "column", gap: "8px" }}>
          <div
            style={{
              display: "flex",
              fontSize: 28,
              letterSpacing: "6px",
              textTransform: "uppercase",
              color: "#22d3ee",
              fontWeight: 600,
            }}
          >
            Plataforma de estudos com IA
          </div>
          <div style={{ display: "flex", fontSize: 76, fontWeight: 800, lineHeight: 1.05, letterSpacing: "-2px", maxWidth: 980 }}>
            Estude para concursos com Inteligência Artificial.
          </div>
        </div>

        {/* base: chips + url */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", gap: "14px" }}>
            {["Questões das maiores bancas", "Flashcards + IA", "Tutor por aula"].map((t) => (
              <div
                key={t}
                style={{
                  display: "flex",
                  fontSize: 24,
                  color: "#cbd5e1",
                  border: "1px solid rgba(255,255,255,0.14)",
                  background: "rgba(255,255,255,0.04)",
                  padding: "12px 20px",
                  borderRadius: 999,
                }}
              >
                {t}
              </div>
            ))}
          </div>
          <div style={{ display: "flex", fontSize: 26, color: "#94a3b8" }}>studia.witdev.com.br</div>
        </div>
      </div>
    ),
    { ...size },
  );
}

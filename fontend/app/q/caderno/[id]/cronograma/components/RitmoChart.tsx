"use client";
import { useEffect, useRef, useState } from "react";
import type { DiaPlano, ProgressoDia } from "../api";

/**
 * Meta × real acumulado até a prova, em SVG puro. A linha da meta é recessiva
 * (cinza) e a sua curva real é a ênfase (cyan): estar acima da cinza = adiantado,
 * abaixo = atrasado — o veredito do hero, agora no tempo. Crosshair com tooltip
 * no hover/teclado (← →); cores via tokens, funcionam nos dois temas.
 */
export function RitmoChart({ plano, progresso }: {
  plano: DiaPlano[]; progresso: ProgressoDia[];
}) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [hover, setHover] = useState<number | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setWidth(el.clientWidth));
    ro.observe(el);
    setWidth(el.clientWidth);
    return () => ro.disconnect();
  }, []);

  const H = 240;
  const PAD = { t: 20, r: 16, b: 26, l: 44 };

  const n = plano.length;
  const total = n ? plano[n - 1].meta_acumulada : 0;

  // Curva real: acumulado por dia do plano, carregando o último valor conhecido
  // (resoluções anteriores ao início do plano entram como carry-in no dia 0).
  const acumPorData = new Map(progresso.map((p) => [p.data, p.resolvidas]));
  let carry = 0;
  if (n) {
    for (const p of progresso) if (p.data < plano[0].data) carry = p.resolvidas;
  }
  let hojeIdx = plano.findIndex((d) => d.hoje);
  if (hojeIdx < 0) {
    const iso = new Date().toISOString().slice(0, 10);
    hojeIdx = n && iso > plano[n - 1].data ? n - 1 : 0;
  }
  const real: number[] = [];
  let ultimo = carry;
  for (let i = 0; i <= hojeIdx; i++) {
    ultimo = acumPorData.get(plano[i].data) ?? ultimo;
    real.push(ultimo);
  }

  const yMax = Math.max(total, real[real.length - 1] ?? 0, 1);

  if (!n) return null;
  if (width === 0) {
    return <div ref={wrapRef} style={{ height: H }} aria-hidden />;
  }

  const iw = Math.max(width - PAD.l - PAD.r, 1);
  const ih = H - PAD.t - PAD.b;
  const x = (i: number) => PAD.l + (n === 1 ? 0 : (i / (n - 1)) * iw);
  const y = (v: number) => PAD.t + (1 - v / yMax) * ih;

  // Ticks Y em números redondos (~4 linhas)
  const step = (() => {
    const alvo = yMax / 4;
    const mag = Math.pow(10, Math.floor(Math.log10(Math.max(alvo, 1))));
    for (const m of [1, 2, 5, 10]) if (alvo <= m * mag) return m * mag;
    return 10 * mag;
  })();
  const yTicks: number[] = [];
  for (let v = step; v <= yMax; v += step) yTicks.push(v);

  const metaPath = plano.map((d, i) => `${i ? "L" : "M"}${x(i)} ${y(d.meta_acumulada)}`).join(" ");
  const realPath = real.map((v, i) => `${i ? "L" : "M"}${x(i)} ${y(v)}`).join(" ");
  const realArea = real.length > 1
    ? `${realPath} L${x(real.length - 1)} ${y(0)} L${x(0)} ${y(0)} Z`
    : "";

  const fmtDia = (iso: string) => `${iso.slice(8, 10)}/${iso.slice(5, 7)}`;
  const xLabels = [0, Math.round((n - 1) / 3), Math.round((2 * (n - 1)) / 3), n - 1];

  const realFinal = real[real.length - 1] ?? 0;

  function idxFromEvent(e: React.PointerEvent<SVGSVGElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    const px = e.clientX - rect.left;
    return Math.max(0, Math.min(n - 1, Math.round(((px - PAD.l) / iw) * (n - 1))));
  }

  const hv = hover;
  const tooltipX = hv != null ? Math.min(Math.max(x(hv), 70), width - 90) : 0;

  return (
    <div ref={wrapRef} className="relative select-none">
      {/* Legenda (2 séries) */}
      <div className="absolute right-0 -top-1 flex items-center gap-4 text-[11px] text-fg-muted">
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block w-4 h-0.5 rounded" style={{ background: "var(--primary)" }} />
          Você
        </span>
        <span className="flex items-center gap-1.5">
          <span aria-hidden className="inline-block w-4 h-0.5 rounded" style={{ background: "var(--text-faint)" }} />
          Meta
        </span>
      </div>

      <svg
        width={width}
        height={H}
        role="img"
        aria-label={`Ritmo: você resolveu ${realFinal} de ${total} questões; a meta até hoje é ${plano[hojeIdx].meta_acumulada}.`}
        tabIndex={0}
        className="focus-visible:outline-2 focus-visible:outline-primary rounded"
        onPointerMove={(e) => setHover(idxFromEvent(e))}
        onPointerLeave={() => setHover(null)}
        onKeyDown={(e) => {
          if (e.key === "ArrowRight") { setHover((h) => Math.min((h ?? hojeIdx) + 1, n - 1)); e.preventDefault(); }
          if (e.key === "ArrowLeft") { setHover((h) => Math.max((h ?? hojeIdx) - 1, 0)); e.preventDefault(); }
          if (e.key === "Escape") setHover(null);
        }}
      >
        {/* grade horizontal (hairlines sólidas, recessivas) */}
        {yTicks.map((v) => (
          <g key={v}>
            <line x1={PAD.l} x2={width - PAD.r} y1={y(v)} y2={y(v)} stroke="var(--border-default)" strokeWidth={1} />
            <text x={PAD.l - 8} y={y(v) + 3.5} textAnchor="end" fontSize={10} fill="var(--text-faint)" style={{ fontVariantNumeric: "tabular-nums" }}>
              {v.toLocaleString("pt-BR")}
            </text>
          </g>
        ))}
        <line x1={PAD.l} x2={width - PAD.r} y1={y(0)} y2={y(0)} stroke="var(--border-strong)" strokeWidth={1} />

        {/* rótulos do eixo X */}
        {xLabels.map((i) => (
          <text key={i} x={x(i)} y={H - 8} textAnchor="middle" fontSize={10} fill="var(--text-faint)">
            {fmtDia(plano[i].data)}
          </text>
        ))}

        {/* hoje */}
        <line x1={x(hojeIdx)} x2={x(hojeIdx)} y1={PAD.t - 4} y2={y(0)} stroke="var(--border-strong)" strokeWidth={1} />
        <text x={x(hojeIdx)} y={PAD.t - 8} textAnchor="middle" fontSize={10} fill="var(--text-muted)">hoje</text>

        {/* meta (recessiva) */}
        <path d={metaPath} fill="none" stroke="var(--text-faint)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />

        {/* você (ênfase) */}
        {realArea && <path d={realArea} fill="var(--primary)" opacity={0.1} />}
        <path d={realPath} fill="none" stroke="var(--primary)" strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        <circle cx={x(real.length - 1)} cy={y(realFinal)} r={4.5} fill="var(--primary)" stroke="var(--surface-card)" strokeWidth={2} />

        {/* rótulos diretos: só os dois pontos que importam */}
        <text x={Math.min(x(real.length - 1) + 8, width - PAD.r)} y={y(realFinal) - 8} fontSize={11} fontWeight={600} fill="var(--text-body)">
          {realFinal.toLocaleString("pt-BR")}
        </text>
        <text x={width - PAD.r} y={y(total) - 6} textAnchor="end" fontSize={10} fill="var(--text-faint)">
          {total.toLocaleString("pt-BR")} na prova
        </text>

        {/* crosshair */}
        {hv != null && (
          <g pointerEvents="none">
            <line x1={x(hv)} x2={x(hv)} y1={PAD.t} y2={y(0)} stroke="var(--text-faint)" strokeWidth={1} />
            <circle cx={x(hv)} cy={y(plano[hv].meta_acumulada)} r={3.5} fill="var(--text-faint)" stroke="var(--surface-card)" strokeWidth={2} />
            {hv < real.length && (
              <circle cx={x(hv)} cy={y(real[hv])} r={3.5} fill="var(--primary)" stroke="var(--surface-card)" strokeWidth={2} />
            )}
          </g>
        )}
      </svg>

      {/* tooltip: valores primeiro, série depois */}
      {hv != null && (
        <div
          className="absolute z-10 pointer-events-none bg-surface-2 border border-border rounded-md shadow-md px-3 py-2 text-xs"
          style={{ left: tooltipX, top: 8, transform: "translateX(-50%)" }}
        >
          <div className="text-fg-faint mb-1">{fmtDia(plano[hv].data)}</div>
          {hv < real.length && (
            <div className="flex items-center gap-1.5">
              <span aria-hidden className="inline-block w-3 h-0.5 rounded" style={{ background: "var(--primary)" }} />
              <span className="font-semibold text-fg tabular-nums">{real[hv]}</span>
              <span className="text-fg-muted">você</span>
            </div>
          )}
          <div className="flex items-center gap-1.5">
            <span aria-hidden className="inline-block w-3 h-0.5 rounded" style={{ background: "var(--text-faint)" }} />
            <span className="font-semibold text-fg tabular-nums">{plano[hv].meta_acumulada}</span>
            <span className="text-fg-muted">meta</span>
          </div>
        </div>
      )}
    </div>
  );
}

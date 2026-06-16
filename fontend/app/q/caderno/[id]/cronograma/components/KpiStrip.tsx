"use client";
import type { Kpis } from "../api";

export function KpiStrip({ kpis, diasAteProva }: { kpis: Kpis; diasAteProva: number }) {
  const saldo = kpis.saldo;
  const saldoLabel = saldo >= 0 ? `+${saldo} adiantado` : `${saldo} atrasado`;
  const cards = [
    { label: "Conclusão", value: `${Math.round(kpis.pct_conclusao * 100)}%`, sub: `${kpis.resolvidas}/${kpis.total}` },
    { label: "Acerto", value: `${Math.round(kpis.pct_acerto * 100)}%`, sub: `${kpis.acertos} acertos` },
    { label: "Saldo vs meta", value: saldoLabel, sub: `meta hoje: ${kpis.meta_hoje}` },
    { label: "Ritmo necessário", value: `${kpis.questoes_dia_necessarias}/dia`, sub: `${kpis.dias_uteis_restantes} dias úteis` },
    { label: "Dias até a prova", value: String(diasAteProva), sub: "" },
  ];
  return (
    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
      {cards.map((c) => (
        <div key={c.label} className="bg-surface border border-border/60 rounded-lg p-3">
          <div className="text-xs text-fg-faint">{c.label}</div>
          <div className={`text-lg font-semibold ${c.label === "Saldo vs meta" && saldo < 0 ? "text-error" : "text-fg"}`}>{c.value}</div>
          <div className="text-xs text-fg-muted">{c.sub}</div>
        </div>
      ))}
    </div>
  );
}

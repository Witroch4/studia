"use client";
import type { Kpis } from "../api";

/**
 * Veredito do dia em linguagem clara ("você está adiantado/atrasado") + régua
 * de progresso com o marcador da meta de hoje — o saldo vira distância visual
 * entre o preenchimento (resolvidas) e o tick (meta), não só um número.
 */
export function VereditoHero({ kpis, diasAteProva, dataProva }: {
  kpis: Kpis; diasAteProva: number; dataProva: string;
}) {
  const { saldo, meta_hoje, resolvidas, total } = kpis;
  const emDia = saldo === 0;
  const adiantado = saldo > 0;

  const pctResolvidas = total > 0 ? (resolvidas / total) * 100 : 0;
  const pctMeta = total > 0 ? Math.min((meta_hoje / total) * 100, 100) : 0;

  const provaFmt = new Date(`${dataProva}T12:00:00`).toLocaleDateString("pt-BR", {
    day: "2-digit", month: "short",
  });

  const subKpis = [
    { label: "Conclusão", value: `${Math.round(kpis.pct_conclusao * 100)}%`, sub: `${resolvidas}/${total}` },
    { label: "Acerto", value: `${Math.round(kpis.pct_acerto * 100)}%`, sub: `${kpis.acertos} certas` },
    { label: "Ritmo p/ terminar", value: `${kpis.questoes_dia_necessarias}/dia`, sub: `${kpis.dias_uteis_restantes} dias úteis` },
    { label: "Prova", value: `${diasAteProva} dias`, sub: provaFmt },
  ];

  return (
    <section className="bg-surface border border-border/60 rounded-xl p-5">
      <div className="flex flex-col lg:flex-row lg:items-start gap-5">
        {/* ── Veredito ── */}
        <div className="flex-1 min-w-0">
          <p className="text-xs text-fg-faint mb-1">Onde você está hoje</p>
          <p className="text-2xl md:text-3xl font-semibold text-fg-strong leading-tight">
            {emDia ? (
              <>Você está <span className="text-success">em dia</span> com a meta</>
            ) : adiantado ? (
              <>Você está <span className="text-success">{saldo} {saldo === 1 ? "questão" : "questões"} à frente</span> da meta</>
            ) : (
              <>Você está <span className="text-error">{-saldo} {saldo === -1 ? "questão" : "questões"} atrás</span> da meta</>
            )}
          </p>
          <p className="text-sm text-fg-muted mt-1">
            Meta até hoje: {meta_hoje} resolvidas · você resolveu {resolvidas}.
            {kpis.anuladas > 0 && ` ${kpis.anuladas} ${kpis.anuladas === 1 ? "anulada fora" : "anuladas fora"} da conta.`}
            {!adiantado && !emDia && " Dá para recuperar aumentando o ritmo ou recalculando o plano."}
          </p>

          {/* Régua: preenchimento = resolvidas; tick = meta de hoje */}
          <div className="mt-4" aria-hidden>
            <div className="relative h-2.5 rounded-full bg-fg/10">
              <div
                className={`absolute inset-y-0 left-0 rounded-full ${adiantado || emDia ? "bg-success" : "bg-error"}`}
                style={{ width: `${pctResolvidas}%` }}
              />
              <div
                className="absolute -top-1 -bottom-1 w-0.5 bg-fg-strong/80 rounded-full"
                style={{ left: `${pctMeta}%` }}
                title={`Meta de hoje: ${meta_hoje}`}
              />
            </div>
            <div className="relative mt-1 h-4 text-[11px] text-fg-faint">
              <span className="absolute left-0">0</span>
              <span className="absolute -translate-x-1/2" style={{ left: `${pctMeta}%` }}>
                meta {meta_hoje}
              </span>
              <span className="absolute right-0">{total}</span>
            </div>
          </div>
        </div>

        {/* ── KPIs de apoio ── */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-2 gap-2 lg:w-72 shrink-0">
          {subKpis.map((k) => (
            <div key={k.label} className="bg-inset border border-border/40 rounded-lg px-3 py-2">
              <div className="text-[11px] text-fg-faint">{k.label}</div>
              <div className="text-base font-semibold text-fg">{k.value}</div>
              <div className="text-[11px] text-fg-muted">{k.sub}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}

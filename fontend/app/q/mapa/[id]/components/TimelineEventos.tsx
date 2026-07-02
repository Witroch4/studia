"use client";

// ─── Tipos ───────────────────────────────────────────────

export interface Evento {
  titulo: string;
  data_inicio: string | null;
  data_fim: string | null;
  tipo: string;
}

// ─── Helpers ─────────────────────────────────────────────

const ICONES: Record<string, string> = {
  inscricao: "edit_calendar",
  prova: "quiz",
  resultado: "flag",
  recurso: "gavel",
  isencao: "request_quote",
  homologacao: "verified",
  outro: "event",
};

function formatarData(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString("pt-BR");
}

/** Dias até a data (0 = hoje; negativo = já passou; null = sem data). */
function diasAte(iso: string | null): number | null {
  if (!iso) return null;
  const hoje = new Date();
  hoje.setHours(0, 0, 0, 0);
  const alvo = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(alvo.getTime())) return null;
  return Math.round((alvo.getTime() - hoje.getTime()) / 86_400_000);
}

/** Ordena por data_inicio crescente, eventos sem data vão para o fim. */
function ordenarEventos(eventos: Evento[]): Evento[] {
  return [...eventos].sort((a, b) => {
    if (!a.data_inicio && !b.data_inicio) return 0;
    if (!a.data_inicio) return 1;
    if (!b.data_inicio) return -1;
    return a.data_inicio.localeCompare(b.data_inicio);
  });
}

// ─── Componente ──────────────────────────────────────────

/**
 * Linha do tempo do edital: inscrição, prova, resultado, recurso, isenção,
 * homologação e outras datas relevantes, ordenadas cronologicamente. Eventos
 * a ≤ 7 dias ganham destaque visual (o usuário precisa ver isso de cara).
 */
export function TimelineEventos({ eventos }: { eventos: Evento[] }) {
  const ordenados = ordenarEventos(eventos);

  if (ordenados.length === 0) {
    return (
      <div className="rounded-xl border border-border bg-surface p-6 text-center text-sm text-fg-muted">
        Nenhuma data divulgada no edital ainda.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-border bg-surface p-4">
      <h2 className="text-sm font-semibold text-fg-strong mb-3 flex items-center gap-2">
        <span className="material-symbols-outlined text-[18px] text-primary">event_note</span>
        Datas do edital
      </h2>
      <ol className="space-y-1">
        {ordenados.map((ev, i) => {
          const dias = diasAte(ev.data_inicio);
          const destaque = dias !== null && dias >= 0 && dias <= 7;
          return (
            <li
              key={`${ev.titulo}-${i}`}
              className={`flex items-start gap-3 rounded-lg px-2 py-2 ${destaque ? "bg-warning/10" : ""}`}
            >
              <span
                className={`material-symbols-outlined text-[18px] shrink-0 mt-0.5 ${
                  destaque ? "text-warning" : "text-fg-faint"
                }`}
              >
                {ICONES[ev.tipo] ?? ICONES.outro}
              </span>
              <div className="min-w-0">
                <p className={`text-sm font-medium ${destaque ? "text-fg-strong" : "text-fg"}`}>
                  {ev.titulo || "Evento"}
                </p>
                <p className="text-xs text-fg-faint">
                  {formatarData(ev.data_inicio) || "Data não informada"}
                  {ev.data_fim && ev.data_fim !== ev.data_inicio ? ` – ${formatarData(ev.data_fim)}` : ""}
                  {destaque && <span className="text-warning font-medium"> · em breve</span>}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

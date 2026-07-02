"use client";

import { useMemo, useState } from "react";
import Link from "next/link";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiJson, apiPost } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import { Skeleton } from "@/app/components/ds";
import { useDerivarCaderno, type TipoDerivar } from "./useDerivarCaderno";

// ════════════════════════════ Tipos ════════════════════════════

interface Resumo {
  questoes_total: number;
  resolvidas: number;
  acertos: number;
  erros: number;
  em_branco: number;
  anuladas: number;
  favoritas: number;
  anotadas: number;
  taxa: number;
  tempo_total_segundos: number;
  tempo_medio_segundos: number;
}

interface NoArvore {
  id: number | null;
  nome: string;
  total: number;
  anuladas: number;
  resolvidas: number;
  acertos: number;
  erros: number;
}

interface MateriaArvore extends NoArvore {
  assuntos: NoArvore[];
}

interface StatsDetalhe {
  resolvidas: number;
  acertos: number;
  erros: number;
  taxa: number;
  questoes_total: number;
  tempo_total_segundos: number;
  tempo_medio_segundos: number;
  resumo: Resumo;
  arvore: MateriaArvore[];
  por_banca: Array<{ nome: string; resolvidas: number; acertos: number; taxa: number }>;
  ultimas_resolucoes: Array<{
    questao_id: number; id_externo?: number; resposta: string; acertou: boolean;
    tempo_segundos: number; created_at: string;
  }>;
}

interface Comunidade {
  usuarios: number;
  resolvidas: number;
  acertos: number;
  erros: number;
  dificuldade: number | null;
}

type Exibicao = "todas" | "resolvidas";
type Pontuacao = "normal" | "liquida";
type TipoZerar = "todas" | "acertadas" | "erradas";

function formatTempo(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = Math.floor(s % 60);
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

const nf = (n: number) => n.toLocaleString("pt-BR");

/** Taxa exibida no centro do donut e na árvore, conforme a pontuação. */
function taxaPct(acertos: number, erros: number, resolvidas: number, pontuacao: Pontuacao): number {
  if (!resolvidas) return 0;
  const base = pontuacao === "liquida" ? acertos - erros : acertos;
  return Math.round((base / resolvidas) * 100);
}

// ════════════════════════════ Donut SVG ════════════════════════════

const TAU = Math.PI * 2;

function pt(cx: number, cy: number, r: number, a: number): [number, number] {
  return [cx + r * Math.cos(a), cy + r * Math.sin(a)];
}

function arcPath(cx: number, cy: number, rO: number, rI: number, a0: number, a1: number) {
  const large = a1 - a0 > Math.PI ? 1 : 0;
  const [x0, y0] = pt(cx, cy, rO, a0);
  const [x1, y1] = pt(cx, cy, rO, a1);
  const [x2, y2] = pt(cx, cy, rI, a1);
  const [x3, y3] = pt(cx, cy, rI, a0);
  return `M${x0} ${y0} A${rO} ${rO} 0 ${large} 1 ${x1} ${y1} L${x2} ${y2} A${rI} ${rI} 0 ${large} 0 ${x3} ${y3} Z`;
}

interface Segmento { label: string; valor: number; cor: string; opacity?: number }

/**
 * Rosca genérica: centro mostra a taxa; hover/foco num segmento troca o centro
 * pelo detalhe. Legenda embaixo — os números nunca dependem só da cor.
 */
function Donut({ segs, centroGrande, centroPequeno, ariaLabel }: {
  segs: Segmento[];
  centroGrande: string;
  centroPequeno: string;
  ariaLabel: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const total = Math.max(segs.reduce((s, x) => s + x.valor, 0), 1);

  const S = 176, cx = S / 2, cy = S / 2, rO = 82, rI = 58;
  const rMid = (rO + rI) / 2;
  const pad = 1 / rMid;

  const visiveis = segs.filter((s) => s.valor > 0);
  const arcos: Array<string | null> = [];
  for (let i = 0, a = -Math.PI / 2; i < segs.length; i++) {
    const s = segs[i];
    if (s.valor <= 0) {
      arcos.push(null);
      continue;
    }
    const span = (s.valor / total) * TAU;
    const gap = visiveis.length > 1 ? pad : 0;
    arcos.push(arcPath(cx, cy, rO, rI, a + gap, Math.max(a + span - gap, a + gap + 0.004)));
    a += span;
  }

  const centro = hover != null && segs[hover].valor > 0
    ? { grande: nf(segs[hover].valor), pequeno: segs[hover].label.toLowerCase() }
    : { grande: centroGrande, pequeno: centroPequeno };

  return (
    <div className="flex flex-col items-center gap-3">
      <svg width={S} height={S} role="img" aria-label={ariaLabel} className="shrink-0">
        {visiveis.length === 0 && (
          <circle cx={cx} cy={cy} r={rMid} fill="none" stroke="var(--border-default)" strokeWidth={rO - rI} />
        )}
        {segs.map((s, i) =>
          arcos[i] ? (
            <path
              key={s.label}
              d={arcos[i]!}
              fill={s.cor}
              opacity={hover != null && hover !== i ? 0.35 : (s.opacity ?? 1)}
              className="transition-opacity cursor-default focus-visible:outline-2 focus-visible:outline-primary"
              tabIndex={0}
              role="img"
              aria-label={`${s.label}: ${s.valor}`}
              onPointerEnter={() => setHover(i)}
              onPointerLeave={() => setHover(null)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
            >
              <title>{`${s.label}: ${nf(s.valor)}`}</title>
            </path>
          ) : null
        )}
        <text x={cx} y={cy - 2} textAnchor="middle" fontSize={27} fontWeight={700} fill="var(--text-strong)">
          {centro.grande}
        </text>
        <text x={cx} y={cy + 18} textAnchor="middle" fontSize={11} fill="var(--text-muted)">
          {centro.pequeno}
        </text>
      </svg>
      <ul className="grid grid-cols-2 gap-x-5 gap-y-1 text-xs">
        {segs.map((s, i) => (
          <li
            key={s.label}
            className="flex items-center gap-1.5"
            onPointerEnter={() => setHover(i)}
            onPointerLeave={() => setHover(null)}
          >
            <span aria-hidden className="w-2.5 h-2.5 rounded-[3px] shrink-0" style={{ background: s.cor, opacity: s.opacity ?? 1 }} />
            <span className="text-fg-muted">{s.label}</span>
            <span className="ml-auto font-semibold text-fg tabular-nums">{nf(s.valor)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ════════════════════════════ Painel resumo ════════════════════════════

function LinhaResumo({ label, valor, cor, indent, mono, acoes }: {
  label: string;
  valor: string;
  cor?: string;
  indent?: boolean;
  mono?: boolean;
  acoes?: React.ReactNode;
}) {
  return (
    <li className={`group flex items-center gap-2 py-2 ${indent ? "pl-5" : ""}`}>
      {indent && <span aria-hidden className="text-fg-faint -ml-3">↳</span>}
      <span className={`text-sm ${cor ?? "text-fg-muted"}`}>{label}</span>
      <span className="ml-auto flex items-center gap-1">
        {acoes}
        <span className={`min-w-14 text-right text-sm font-semibold tabular-nums ${mono ? "font-mono" : ""} ${cor ?? "text-fg"}`}>
          {valor}
        </span>
      </span>
    </li>
  );
}

function AcaoIcone({ icone, title, onClick, disabled }: {
  icone: string; title: string; onClick: () => void; disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-label={title}
      className="flex h-7 w-7 items-center justify-center rounded-md text-fg-faint opacity-0 transition group-hover:opacity-100 focus-visible:opacity-100 hover:bg-surface-2 hover:text-primary disabled:pointer-events-none disabled:opacity-0"
    >
      <span className="material-symbols-outlined" style={{ fontSize: 17 }}>{icone}</span>
    </button>
  );
}

// ════════════════════════════ Comunidade ════════════════════════════

function ComunidadeCard({ cadernoId }: { cadernoId: number }) {
  const [exibir, setExibir] = useState(false);
  const { data, isPending } = useQuery<Comunidade>({
    queryKey: qk.cadernoSub(cadernoId, "stats-comunidade"),
    queryFn: () => apiJson(`/api/q/cadernos/${cadernoId}/stats-comunidade`),
    enabled: exibir,
    staleTime: 5 * 60_000,
  });

  // Espaço do donut é reservado SEMPRE (nada pula quando os dados chegam).
  if (!exibir) {
    return (
      <div className="flex flex-col items-center gap-3">
        <div className="flex h-44 w-44 items-center justify-center rounded-full border-14 border-dashed border-border/70">
          <button
            onClick={() => setExibir(true)}
            className="rounded-lg bg-primary/10 px-4 py-2 text-xs font-semibold text-primary transition hover:bg-primary/20"
          >
            Exibir
          </button>
        </div>
        <p className="h-9 max-w-44 text-center text-[11px] leading-tight text-fg-faint">
          Como os demais usuários se saíram nestas questões
        </p>
      </div>
    );
  }

  if (isPending || !data) {
    return (
      <div className="flex flex-col items-center gap-3">
        <Skeleton className="h-44 w-44 rounded-full" />
        <Skeleton className="h-9 w-40" />
      </div>
    );
  }

  const taxa = data.resolvidas ? Math.round((data.acertos / data.resolvidas) * 100) : 0;
  return (
    <div className="flex flex-col items-center gap-3">
      <Donut
        segs={[
          { label: "Acertos", valor: data.acertos, cor: "var(--success)" },
          { label: "Erros", valor: data.erros, cor: "var(--error)" },
        ]}
        centroGrande={data.resolvidas ? `${taxa}%` : "—"}
        centroPequeno={data.resolvidas ? "de acerto" : "sem dados"}
        ariaLabel={`Demais usuários: ${data.acertos} acertos e ${data.erros} erros em ${data.resolvidas} resoluções.`}
      />
      <p className="h-9 text-center text-[11px] leading-tight text-fg-faint">
        {data.usuarios} {data.usuarios === 1 ? "usuário" : "usuários"} · {nf(data.resolvidas)} resoluções
      </p>
    </div>
  );
}

function DificuldadeBar({ cadernoId }: { cadernoId: number }) {
  // Reusa o cache da comunidade se o usuário clicou em Exibir; senão fica oculto
  // (a dificuldade depende do universo de resoluções, carregado sob demanda).
  const { data } = useQuery<Comunidade>({
    queryKey: qk.cadernoSub(cadernoId, "stats-comunidade"),
    queryFn: () => apiJson(`/api/q/cadernos/${cadernoId}/stats-comunidade`),
    enabled: false,
  });
  if (data?.dificuldade == null) return null;
  const pct = Math.min(Math.max(data.dificuldade, 0), 100);
  return (
    <div className="mt-4 flex items-center gap-3">
      <span className="text-xs text-fg-muted">Dificuldade média do caderno</span>
      <div
        className="relative h-2 w-40 rounded-full"
        style={{ background: "linear-gradient(90deg, var(--success), var(--warning), var(--error))" }}
        role="img"
        aria-label={`Dificuldade média: ${pct}%`}
      >
        <span
          aria-hidden
          className="absolute top-1/2 h-3.5 w-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-page bg-fg-strong shadow"
          style={{ left: `${pct}%` }}
        />
      </div>
      <span className="text-xs font-semibold tabular-nums text-fg">{pct}%</span>
    </div>
  );
}

// ════════════════════════════ Árvore matéria → assunto ════════════════════════════

type Ordem = "indice" | "fortes" | "fracos";

function ordenarNos<T extends NoArvore>(nos: T[], ordem: Ordem): T[] {
  const copia = [...nos];
  if (ordem === "indice") {
    copia.sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"));
    return copia;
  }
  const taxa = (n: NoArvore) => (n.resolvidas ? n.acertos / n.resolvidas : -1);
  copia.sort((a, b) => {
    // Sem resolvidas vai pro fim nas duas ordenações de desempenho.
    if (!a.resolvidas !== !b.resolvidas) return a.resolvidas ? -1 : 1;
    const d = taxa(a) - taxa(b);
    return ordem === "fortes" ? -d : d;
  });
  return copia;
}

function BarraNo({ no, className = "" }: { no: NoArvore; className?: string }) {
  const largura = no.total ? (no.resolvidas / no.total) * 100 : 0;
  const pctAcerto = no.resolvidas ? (no.acertos / no.resolvidas) * 100 : 0;
  return (
    <div className={`h-2 overflow-hidden rounded-full bg-surface-2 ${className}`} aria-hidden>
      <div className="flex h-full" style={{ width: `${largura}%` }}>
        <div className="h-full bg-success" style={{ width: `${pctAcerto}%` }} />
        <div className="h-full bg-error" style={{ width: `${100 - pctAcerto}%` }} />
      </div>
    </div>
  );
}

function TextoDesempenho({ no, pontuacao }: { no: NoArvore; pontuacao: Pontuacao }) {
  if (!no.resolvidas) return <span className="text-xs text-fg-faint tabular-nums">0%</span>;
  if (pontuacao === "liquida") {
    const pct = taxaPct(no.acertos, no.erros, no.resolvidas, "liquida");
    return (
      <span className={`text-xs font-semibold tabular-nums ${pct >= 0 ? "text-success" : "text-error"}`}>
        {pct}% líq.
      </span>
    );
  }
  const pa = Math.round((no.acertos / no.resolvidas) * 100);
  return (
    <span className="whitespace-nowrap text-xs tabular-nums">
      <span className="font-semibold text-success">{pa}%</span>
      <span className="text-fg-faint"> ({no.acertos})</span>
      <span className="ml-1.5 font-semibold text-error">{100 - pa}%</span>
      <span className="text-fg-faint"> ({no.erros})</span>
    </span>
  );
}

function ArvoreDesempenho({ arvore, pontuacao, apenasResolvidas, onCriarSelecao }: {
  arvore: MateriaArvore[];
  pontuacao: Pontuacao;
  apenasResolvidas: boolean;
  onCriarSelecao: (tipo: TipoDerivar, materiaIds: number[], assuntoIds: number[]) => void;
}) {
  const [ordem, setOrdem] = useState<Ordem>("indice");
  const [mostrarGrafico, setMostrarGrafico] = useState(true);
  const [mostrarTexto, setMostrarTexto] = useState(true);
  const [abertas, setAbertas] = useState<Set<number | null>>(() => new Set(arvore.length === 1 ? [arvore[0]?.id ?? null] : []));
  const [selMaterias, setSelMaterias] = useState<Set<number>>(new Set());
  const [selAssuntos, setSelAssuntos] = useState<Set<number>>(new Set());

  const materias = useMemo(() => {
    const base = apenasResolvidas ? arvore.filter((m) => m.resolvidas > 0) : arvore;
    return ordenarNos(base, ordem).map((m) => ({
      ...m,
      assuntos: ordenarNos(apenasResolvidas ? m.assuntos.filter((a) => a.resolvidas > 0) : m.assuntos, ordem),
    }));
  }, [arvore, ordem, apenasResolvidas]);

  function toggleMateria(m: MateriaArvore) {
    setSelMaterias((prev) => {
      const nova = new Set(prev);
      if (m.id == null) return nova;
      if (nova.has(m.id)) nova.delete(m.id);
      else {
        nova.add(m.id);
        // Matéria cobre os assuntos dela: tira da seleção fina.
        setSelAssuntos((sa) => {
          const s = new Set(sa);
          m.assuntos.forEach((a) => a.id != null && s.delete(a.id));
          return s;
        });
      }
      return nova;
    });
  }

  function toggleAssunto(a: NoArvore) {
    if (a.id == null) return;
    setSelAssuntos((prev) => {
      const nova = new Set(prev);
      if (nova.has(a.id!)) nova.delete(a.id!);
      else nova.add(a.id!);
      return nova;
    });
  }

  const selecao = useMemo(() => {
    let resolvidas = 0, acertos = 0, erros = 0;
    for (const m of arvore) {
      if (m.id != null && selMaterias.has(m.id)) {
        resolvidas += m.resolvidas; acertos += m.acertos; erros += m.erros;
        continue; // assuntos da matéria já estão cobertos
      }
      for (const a of m.assuntos) {
        if (a.id != null && selAssuntos.has(a.id)) {
          resolvidas += a.resolvidas; acertos += a.acertos; erros += a.erros;
        }
      }
    }
    return { resolvidas, acertos, erros, vazia: selMaterias.size === 0 && selAssuntos.size === 0 };
  }, [arvore, selMaterias, selAssuntos]);

  function criar(tipo: TipoDerivar) {
    onCriarSelecao(tipo, [...selMaterias], [...selAssuntos]);
  }

  const radioCls = "flex cursor-pointer items-center gap-1.5 text-xs text-fg-muted hover:text-fg";

  return (
    <section className="rounded-xl border border-border/60 bg-surface">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-border/60 px-5 py-3.5">
        <h3 className="text-sm font-semibold text-fg">Desempenho por matéria e assunto</h3>
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <fieldset className="flex items-center gap-3">
            <legend className="sr-only">Ordem de exibição</legend>
            <span className="text-xs text-fg-faint">Ordenar:</span>
            {([["indice", "Índice"], ["fortes", "Pontos fortes"], ["fracos", "Pontos fracos"]] as const).map(([v, l]) => (
              <label key={v} className={radioCls}>
                <input
                  type="radio"
                  name="ordem-arvore"
                  checked={ordem === v}
                  onChange={() => setOrdem(v)}
                  className="accent-primary"
                />
                {l}
              </label>
            ))}
          </fieldset>
          <fieldset className="flex items-center gap-3">
            <legend className="sr-only">O que exibir</legend>
            <span className="text-xs text-fg-faint">Exibir:</span>
            <label className={radioCls}>
              <input type="checkbox" checked={mostrarGrafico} onChange={(e) => setMostrarGrafico(e.target.checked)} className="accent-primary" />
              Gráfico
            </label>
            <label className={radioCls}>
              <input type="checkbox" checked={mostrarTexto} onChange={(e) => setMostrarTexto(e.target.checked)} className="accent-primary" />
              Texto
            </label>
          </fieldset>
        </div>
      </header>

      <ul className="divide-y divide-border/40 px-2 py-1">
        {materias.length === 0 && (
          <li className="px-3 py-6 text-center text-sm text-fg-faint">Nenhuma matéria com resolução ainda.</li>
        )}
        {materias.map((m) => {
          const aberta = abertas.has(m.id);
          const selecionada = m.id != null && selMaterias.has(m.id);
          return (
            <li key={m.id ?? "sem-materia"}>
              <div className="group flex items-center gap-2 rounded-lg px-2 py-2 hover:bg-surface-2/40">
                <input
                  type="checkbox"
                  checked={selecionada}
                  onChange={() => toggleMateria(m)}
                  disabled={m.id == null}
                  aria-label={`Selecionar ${m.nome}`}
                  className="accent-primary"
                />
                <button
                  onClick={() => setAbertas((prev) => {
                    const nova = new Set(prev);
                    if (nova.has(m.id)) nova.delete(m.id); else nova.add(m.id);
                    return nova;
                  })}
                  disabled={m.assuntos.length === 0}
                  aria-expanded={aberta}
                  className="flex min-w-0 flex-1 items-center gap-1.5 text-left disabled:cursor-default"
                >
                  <span
                    aria-hidden
                    className={`material-symbols-outlined shrink-0 text-fg-faint transition-transform ${aberta ? "rotate-90" : ""} ${m.assuntos.length === 0 ? "opacity-0" : ""}`}
                    style={{ fontSize: 16 }}
                  >
                    chevron_right
                  </span>
                  <span className="truncate text-sm font-medium text-fg">{m.nome}</span>
                  {m.anuladas > 0 && (
                    <span className="shrink-0 text-[10px] text-warning/80">{m.anuladas} anulada{m.anuladas > 1 ? "s" : ""}</span>
                  )}
                </button>
                <span className="hidden shrink-0 text-xs tabular-nums text-fg-faint sm:block">
                  {nf(m.resolvidas)} de {nf(m.total)}
                </span>
                {mostrarGrafico && <BarraNo no={m} className="w-28 shrink-0 sm:w-40" />}
                {mostrarTexto && <span className="min-w-28 shrink-0 text-right"><TextoDesempenho no={m} pontuacao={pontuacao} /></span>}
              </div>

              {aberta && m.assuntos.map((a) => {
                const selAss = a.id != null && (selAssuntos.has(a.id) || selecionada);
                return (
                  <div key={a.id} className="group flex items-center gap-2 rounded-lg py-1.5 pl-10 pr-2 hover:bg-surface-2/40">
                    <input
                      type="checkbox"
                      checked={selAss}
                      disabled={selecionada || a.id == null}
                      onChange={() => toggleAssunto(a)}
                      aria-label={`Selecionar ${a.nome}`}
                      className="accent-primary"
                    />
                    <span className="min-w-0 flex-1 truncate text-[13px] text-fg-muted">{a.nome}</span>
                    <span className="hidden shrink-0 text-xs tabular-nums text-fg-faint sm:block">
                      {nf(a.resolvidas)} de {nf(a.total)}
                    </span>
                    {mostrarGrafico && <BarraNo no={a} className="w-28 shrink-0 sm:w-40" />}
                    {mostrarTexto && <span className="min-w-28 shrink-0 text-right"><TextoDesempenho no={a} pontuacao={pontuacao} /></span>}
                  </div>
                );
              })}
            </li>
          );
        })}
      </ul>

      <footer className="flex flex-wrap items-center gap-3 border-t border-border/60 px-5 py-3.5">
        <p className="text-xs text-fg-muted">
          <span className="font-semibold text-fg">Seleção</span>{" "}
          — Resolvidas: <span className="tabular-nums">{nf(selecao.resolvidas)}</span>
          {" · "}Acertos: <span className="tabular-nums text-success">{nf(selecao.acertos)}</span>
          {" · "}Erros: <span className="tabular-nums text-error">{nf(selecao.erros)}</span>
        </p>
        <div className="ml-auto flex gap-2">
          <button
            onClick={() => criar("resolvidas")}
            disabled={selecao.vazia || selecao.resolvidas === 0}
            className="rounded-lg bg-success/15 px-3.5 py-2 text-xs font-semibold text-success transition hover:bg-success/25 disabled:opacity-35 disabled:pointer-events-none"
          >
            Criar caderno com resolvidas
          </button>
          <button
            onClick={() => criar("erradas")}
            disabled={selecao.vazia || selecao.erros === 0}
            className="rounded-lg bg-error/15 px-3.5 py-2 text-xs font-semibold text-error transition hover:bg-error/25 disabled:opacity-35 disabled:pointer-events-none"
          >
            Criar caderno com erradas
          </button>
        </div>
      </footer>
    </section>
  );
}

// ════════════════════════════ Skeleton (formato final) ════════════════════════════

function EstatisticasSkeleton() {
  return (
    <main className="mx-auto max-w-6xl space-y-5 px-6 py-6">
      <section className="grid gap-5 lg:grid-cols-[340px_1fr]">
        <div className="space-y-3 rounded-xl border border-border/60 bg-surface p-5">
          {Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-6" />)}
        </div>
        <div className="rounded-xl border border-border/60 bg-surface p-5">
          <Skeleton className="mb-5 h-6 w-72" />
          <div className="flex flex-wrap justify-around gap-6">
            <Skeleton className="h-44 w-44 rounded-full" />
            <Skeleton className="h-44 w-44 rounded-full" />
          </div>
        </div>
      </section>
      <Skeleton className="h-72 rounded-xl" />
    </main>
  );
}

// ════════════════════════════ Tela ════════════════════════════

export function EstatisticasTab({ cadernoId, cadernoNome }: { cadernoId: number; cadernoNome: string }) {
  const queryClient = useQueryClient();
  const { data, isPending } = useQuery<StatsDetalhe>({
    queryKey: qk.cadernoSub(cadernoId, "stats-detalhe"),
    queryFn: () => apiJson(`/api/q/cadernos/${cadernoId}/stats-detalhe`),
    staleTime: 30_000,
  });

  const { abrirDialog, modais } = useDerivarCaderno(cadernoId, cadernoNome);
  const [exibicao, setExibicao] = useState<Exibicao>("todas");
  const [pontuacao, setPontuacao] = useState<Pontuacao>("normal");
  const [zerar, setZerar] = useState<TipoZerar | null>(null);

  const zerarMutation = useMutation({
    mutationFn: (tipo: TipoZerar) =>
      apiPost<{ apagadas: number }>(`/api/q/cadernos/${cadernoId}/zerar-resolucoes`, { tipo }),
    onSuccess: (res) => {
      setZerar(null);
      toast.success(`${res.apagadas} ${res.apagadas === 1 ? "resolução apagada" : "resoluções apagadas"}.`);
      // Tudo do caderno depende das resoluções (stats, gabarito, navegação).
      queryClient.invalidateQueries({ queryKey: qk.caderno(cadernoId) });
    },
    onError: (e: unknown) => {
      toast.error(e instanceof Error ? e.message : "Não foi possível zerar as resoluções.");
    },
  });

  if (isPending || !data) return <EstatisticasSkeleton />;

  const r = data.resumo;
  const taxaCentro = taxaPct(r.acertos, r.erros, r.resolvidas, pontuacao);

  const segsUsuario: Segmento[] = exibicao === "resolvidas"
    ? [
        { label: "Acertos", valor: r.acertos, cor: "var(--success)" },
        { label: "Erros", valor: r.erros, cor: "var(--error)" },
      ]
    : [
        { label: "Acertos", valor: r.acertos, cor: "var(--success)" },
        { label: "Erros", valor: r.erros, cor: "var(--error)" },
        { label: "Em branco", valor: r.em_branco, cor: "var(--text-faint)", opacity: 0.35 },
        { label: "Anuladas", valor: r.anuladas, cor: "var(--warning)", opacity: 0.7 },
      ];

  const radioCls = "flex cursor-pointer items-center gap-1.5 text-xs text-fg-muted hover:text-fg";
  const ZERAR_LABEL: Record<TipoZerar, string> = {
    todas: "todas as resoluções",
    acertadas: "as resoluções certas",
    erradas: "as resoluções erradas",
  };

  return (
    <main className="mx-auto max-w-6xl space-y-5 px-6 py-6">
      <section className="grid gap-5 lg:grid-cols-[340px_1fr]">
        {/* ─── Painel resumo (cada linha é acionável) ─── */}
        <div className="rounded-xl border border-border/60 bg-surface px-5 py-2.5">
          <ul className="divide-y divide-border/40">
            <LinhaResumo
              label="Questões"
              valor={nf(r.questoes_total)}
              acoes={
                <AcaoIcone icone="library_add" title="Clonar caderno (sem as resoluções)"
                  onClick={() => abrirDialog("todas")} disabled={r.questoes_total === 0} />
              }
            />
            <LinhaResumo
              label="Resolvidas"
              valor={nf(r.resolvidas)}
              acoes={<>
                <AcaoIcone icone="library_add" title="Criar caderno com as resolvidas"
                  onClick={() => abrirDialog("resolvidas")} disabled={r.resolvidas === 0} />
                <AcaoIcone icone="restart_alt" title="Zerar todas as resoluções"
                  onClick={() => setZerar("todas")} disabled={r.resolvidas === 0} />
              </>}
            />
            <LinhaResumo
              label="Acertos" cor="text-success" indent
              valor={nf(r.acertos)}
              acoes={<>
                <AcaoIcone icone="library_add" title="Criar caderno com as que acertou"
                  onClick={() => abrirDialog("acertadas")} disabled={r.acertos === 0} />
                <AcaoIcone icone="restart_alt" title="Zerar as resoluções certas"
                  onClick={() => setZerar("acertadas")} disabled={r.acertos === 0} />
              </>}
            />
            <LinhaResumo
              label="Erros" cor="text-error" indent
              valor={nf(r.erros)}
              acoes={<>
                <AcaoIcone icone="library_add" title="Criar caderno com as que errou"
                  onClick={() => abrirDialog("erradas")} disabled={r.erros === 0} />
                <AcaoIcone icone="restart_alt" title="Zerar as resoluções erradas"
                  onClick={() => setZerar("erradas")} disabled={r.erros === 0} />
              </>}
            />
            <LinhaResumo
              label="Em branco"
              valor={nf(r.em_branco)}
              acoes={
                <AcaoIcone icone="library_add" title="Criar caderno com as não resolvidas"
                  onClick={() => abrirDialog("em_branco")} disabled={r.em_branco === 0} />
              }
            />
            <LinhaResumo label="Anuladas" cor="text-warning" valor={nf(r.anuladas)} />
            <LinhaResumo
              label="Favoritas"
              valor={nf(r.favoritas)}
              acoes={
                <AcaoIcone icone="library_add" title="Criar caderno com as favoritas"
                  onClick={() => abrirDialog("favoritas")} disabled={r.favoritas === 0} />
              }
            />
            <LinhaResumo
              label="Anotadas"
              valor={nf(r.anotadas)}
              acoes={
                <AcaoIcone icone="library_add" title="Criar caderno com as anotadas"
                  onClick={() => abrirDialog("anotadas")} disabled={r.anotadas === 0} />
              }
            />
            <LinhaResumo label="Tempo total gasto" valor={formatTempo(r.tempo_total_segundos)} mono />
            <LinhaResumo
              label="Tempo médio por questão"
              valor={r.tempo_medio_segundos > 0 ? formatTempo(r.tempo_medio_segundos) : "—"}
              mono
            />
          </ul>
        </div>

        {/* ─── Donuts ─── */}
        <div className="rounded-xl border border-border/60 bg-surface p-5">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <fieldset className="flex items-center gap-3">
              <legend className="sr-only">O que exibir no gráfico</legend>
              <span className="text-xs text-fg-faint">Exibir:</span>
              {([["todas", "Todas"], ["resolvidas", "Apenas resolvidas"]] as const).map(([v, l]) => (
                <label key={v} className={radioCls}>
                  <input type="radio" name="exibicao-stats" checked={exibicao === v} onChange={() => setExibicao(v)} className="accent-primary" />
                  {l}
                </label>
              ))}
            </fieldset>
            <fieldset className="flex items-center gap-3">
              <legend className="sr-only">Pontuação</legend>
              <span className="text-xs text-fg-faint">Pontuação:</span>
              {([["normal", "Normal"], ["liquida", "Líquida"]] as const).map(([v, l]) => (
                <label key={v} className={radioCls} title={v === "liquida" ? "Acertos menos erros (estilo Cebraspe)" : undefined}>
                  <input type="radio" name="pontuacao-stats" checked={pontuacao === v} onChange={() => setPontuacao(v)} className="accent-primary" />
                  {l}
                </label>
              ))}
            </fieldset>
          </div>

          <div className="mt-5 flex flex-wrap items-start justify-around gap-8">
            <div className="flex flex-col items-center gap-3">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">Seu desempenho</h4>
              <Donut
                segs={segsUsuario}
                centroGrande={r.resolvidas ? `${taxaCentro}%` : "—"}
                centroPequeno={r.resolvidas ? (pontuacao === "liquida" ? "líquida" : "de acerto") : "sem resoluções"}
                ariaLabel={`Seu desempenho: ${r.acertos} acertos, ${r.erros} erros, ${r.em_branco} em branco, ${r.anuladas} anuladas de ${r.questoes_total}.`}
              />
            </div>
            <div className="flex flex-col items-center gap-3">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">Demais usuários</h4>
              <ComunidadeCard cadernoId={cadernoId} />
            </div>
          </div>

          <DificuldadeBar cadernoId={cadernoId} />
        </div>
      </section>

      {/* ─── Árvore matéria → assunto ─── */}
      <ArvoreDesempenho
        arvore={data.arvore}
        pontuacao={pontuacao}
        apenasResolvidas={exibicao === "resolvidas"}
        onCriarSelecao={(tipo, materiaIds, assuntoIds) =>
          abrirDialog(tipo, { materiaIds, assuntoIds, rotulo: "Seleção" })}
      />

      {/* ─── Últimas resoluções ─── */}
      {data.ultimas_resolucoes.length > 0 && (
        <section className="rounded-xl border border-border/60 bg-surface p-5">
          <h3 className="mb-3 text-sm font-semibold text-fg">Últimas 20 resoluções</h3>
          <table className="w-full text-xs">
            <thead className="border-b border-border/60 text-fg-faint">
              <tr>
                <th className="px-2 py-1.5 text-left">Questão</th>
                <th className="px-2 py-1.5 text-left">Resposta</th>
                <th className="px-2 py-1.5 text-left">Resultado</th>
                <th className="px-2 py-1.5 text-right">Tempo</th>
                <th className="px-2 py-1.5 text-right">Quando</th>
              </tr>
            </thead>
            <tbody>
              {data.ultimas_resolucoes.map((res, i) => (
                <tr key={i} className="border-b border-border/60">
                  <td className="px-2 py-1.5 font-mono text-primary">
                    <Link href={`/q/questao/${res.questao_id}`} className="hover:underline">
                      #{res.questao_id}
                    </Link>
                  </td>
                  <td className="px-2 py-1.5 font-mono">{res.resposta}</td>
                  <td className={`px-2 py-1.5 ${res.acertou ? "text-success" : "text-error"}`}>
                    {res.acertou ? "✓ Acerto" : "✗ Erro"}
                  </td>
                  <td className="px-2 py-1.5 text-right text-fg-muted">
                    {res.tempo_segundos ? `${res.tempo_segundos}s` : "—"}
                  </td>
                  <td className="px-2 py-1.5 text-right text-fg-faint">
                    {new Date(res.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {r.resolvidas === 0 && (
        <div className="py-8 text-center text-sm text-fg-faint">
          Resolva algumas questões para ver suas estatísticas aqui.
        </div>
      )}

      {/* ─── Confirmação de zerar ─── */}
      {zerar && (
        <div
          className="fixed inset-0 z-60 flex items-center justify-center bg-black/70 p-4 backdrop-blur-sm"
          role="dialog"
          aria-modal="true"
          onClick={() => !zerarMutation.isPending && setZerar(null)}
        >
          <div className="w-full max-w-md rounded-2xl border border-error/30 bg-surface-dark p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-bold text-fg-strong">Zerar {ZERAR_LABEL[zerar]}?</h2>
            <p className="mt-1 text-sm text-fg-muted">
              As resoluções apagadas saem das suas estatísticas deste caderno e as questões voltam a contar como em branco. Isso não pode ser desfeito.
            </p>
            <div className="mt-5 flex gap-2">
              <button
                onClick={() => zerarMutation.mutate(zerar)}
                disabled={zerarMutation.isPending}
                className="flex-1 rounded-lg bg-error py-2.5 text-sm font-semibold text-white transition hover:opacity-90 disabled:opacity-40"
              >
                {zerarMutation.isPending ? "Zerando…" : "Zerar resoluções"}
              </button>
              <button
                onClick={() => setZerar(null)}
                disabled={zerarMutation.isPending}
                className="rounded-lg border border-border px-4 py-2.5 text-sm text-fg-muted hover:text-fg disabled:opacity-40"
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      {modais}
    </main>
  );
}

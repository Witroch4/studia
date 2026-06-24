"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { apiJson } from "@/lib/api";

interface Caderno {
  id: number;
  nome: string;
  pasta: string | null;
  total: number;
  created_at: string | null;
}

interface Planejamento {
  caderno_id: number;
  nome: string;
  pasta: string | null;
  total: number;
  data_inicio: string;
  data_prova: string;
  dias_para_prova: number;
  resolvidas: number;
  pct_conclusao: number;
  pct_acerto: number;
  saldo: number;
  criado_em: string | null;
}

function fmtData(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

export default function PlanejamentoPage() {
  const [cadernos, setCadernos] = useState<Caderno[]>([]);
  const [planos, setPlanos] = useState<Planejamento[]>([]);
  const [loading, setLoading] = useState(true);
  const [busca, setBusca] = useState("");
  // null = ainda não tocado pelo usuário → abre por padrão se não há planos.
  const [novoToggle, setNovoToggle] = useState<boolean | null>(null);
  const abrirNovo = novoToggle ?? (!loading && planos.length === 0);

  useEffect(() => {
    Promise.all([
      apiJson<Caderno[]>("/api/q/cadernos").catch(() => [] as Caderno[]),
      apiJson<Planejamento[]>("/api/q/cronogramas").catch(() => [] as Planejamento[]),
    ])
      .then(([cads, pls]) => {
        setCadernos(Array.isArray(cads) ? cads : []);
        setPlanos(Array.isArray(pls) ? pls : []);
      })
      .finally(() => setLoading(false));
  }, []);

  const comPlano = useMemo(
    () => new Set(planos.map((p) => p.caderno_id)),
    [planos]
  );

  const cadernosSemPlano = useMemo(() => {
    const t = busca.trim().toLowerCase();
    return cadernos
      .filter((c) => !comPlano.has(c.id))
      .filter((c) => !t || c.nome.toLowerCase().includes(t) || (c.pasta || "").toLowerCase().includes(t));
  }, [cadernos, comPlano, busca]);

  return (
    <div className="min-h-screen bg-page text-fg">
      <div className="border-b border-border/60 px-6 py-2 flex items-center gap-3 text-xs bg-page">
        <span className="text-fg-faint">Estudo</span>
        <span className="text-fg-faint">›</span>
        <span className="text-fg-muted">Planejamento</span>
      </div>

      <main className="max-w-3xl mx-auto px-6 py-6">
        <h1 className="text-xl font-semibold mb-1">Planejamento</h1>
        <p className="text-sm text-fg-muted mb-6">
          Seus cronogramas de estudo. Cada planejamento é vinculado a um caderno.
        </p>

        {loading && <p className="text-sm text-fg-faint">Carregando…</p>}

        {/* ───────── Meus planejamentos ───────── */}
        {!loading && (
          <section className="mb-8">
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold text-fg uppercase tracking-wide">
                Meus planejamentos
                {planos.length > 0 && (
                  <span className="ml-2 text-fg-faint font-normal normal-case">
                    ({planos.length})
                  </span>
                )}
              </h2>
            </div>

            {planos.length === 0 ? (
              <div className="bg-surface border border-dashed border-border/60 rounded-lg px-4 py-6 text-center">
                <p className="text-sm text-fg-muted">
                  Você ainda não criou nenhum planejamento.
                </p>
                <p className="text-xs text-fg-faint mt-1">
                  Escolha um caderno abaixo para gerar seu primeiro cronograma.
                </p>
              </div>
            ) : (
              <div className="grid gap-2">
                {planos.map((p) => {
                  const atrasado = p.saldo < 0;
                  const pct = Math.round(p.pct_conclusao * 100);
                  return (
                    <a
                      key={p.caderno_id}
                      href={`/q/caderno/${p.caderno_id}/cronograma`}
                      className="bg-surface border border-border/60 rounded-lg px-4 py-3 hover:border-primary/40 transition block"
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-fg truncate">{p.nome}</div>
                          {p.pasta && (
                            <div className="text-xs text-fg-faint truncate">{p.pasta}</div>
                          )}
                        </div>
                        <div className="text-right shrink-0">
                          <div className="text-xs text-fg-muted whitespace-nowrap">
                            Prova {fmtData(p.data_prova)}
                          </div>
                          <div
                            className={`text-xs font-medium whitespace-nowrap ${
                              p.dias_para_prova < 0
                                ? "text-fg-faint"
                                : p.dias_para_prova <= 14
                                ? "text-red-400"
                                : "text-fg-muted"
                            }`}
                          >
                            {p.dias_para_prova < 0
                              ? "encerrado"
                              : p.dias_para_prova === 0
                              ? "é hoje!"
                              : `${p.dias_para_prova} dias restantes`}
                          </div>
                        </div>
                      </div>

                      {/* progresso */}
                      <div className="mt-3 flex items-center gap-3">
                        <div className="h-1.5 flex-1 rounded-full bg-border/60 overflow-hidden">
                          <div
                            className="h-full rounded-full bg-primary"
                            style={{ width: `${Math.min(pct, 100)}%` }}
                          />
                        </div>
                        <span className="text-xs text-fg-faint shrink-0 tabular-nums">
                          {pct}% · {p.resolvidas.toLocaleString("pt-BR")}/
                          {p.total.toLocaleString("pt-BR")}
                        </span>
                        <span
                          className={`text-xs font-medium shrink-0 px-1.5 py-0.5 rounded ${
                            atrasado
                              ? "text-red-300 bg-red-500/10"
                              : "text-emerald-300 bg-emerald-500/10"
                          }`}
                        >
                          {atrasado ? `${Math.abs(p.saldo)} atrás` : "em dia"}
                        </span>
                      </div>
                    </a>
                  );
                })}
              </div>
            )}
          </section>
        )}

        {/* ───────── Criar novo ───────── */}
        {!loading && (
          <section>
            <button
              type="button"
              onClick={() => setNovoToggle(!abrirNovo)}
              className="w-full flex items-center justify-between mb-3 text-left"
            >
              <h2 className="text-sm font-semibold text-fg uppercase tracking-wide">
                Criar novo planejamento
              </h2>
              <span className="text-fg-faint text-xs">{abrirNovo ? "ocultar ▲" : "mostrar ▼"}</span>
            </button>

            {abrirNovo && (
              <>
                <p className="text-xs text-fg-muted mb-3">
                  Escolha um caderno para gerar um cronograma de estudo.
                </p>

                {cadernos.length === 0 ? (
                  <p className="text-sm text-fg-faint italic">
                    Nenhum caderno encontrado. Crie um em{" "}
                    <Link href="/q/filtrar" className="text-primary hover:underline">
                      Filtrar Questões
                    </Link>{" "}
                    ou acesse um{" "}
                    <Link href="/q/guias" className="text-primary hover:underline">
                      Guia de Estudos
                    </Link>
                    .
                  </p>
                ) : (
                  <>
                    <input
                      type="text"
                      value={busca}
                      onChange={(e) => setBusca(e.target.value)}
                      placeholder="Buscar caderno…"
                      className="w-full mb-3 bg-surface border border-border/60 rounded-lg px-3 py-2 text-sm text-fg placeholder:text-fg-faint focus:outline-none focus:border-primary/50"
                    />

                    {cadernosSemPlano.length === 0 ? (
                      <p className="text-sm text-fg-faint italic">
                        {busca
                          ? "Nenhum caderno corresponde à busca."
                          : "Todos os cadernos já têm planejamento."}
                      </p>
                    ) : (
                      <div className="grid gap-2 max-h-112 overflow-y-auto pr-1">
                        {cadernosSemPlano.map((c) => (
                          <a
                            key={c.id}
                            href={`/q/caderno/${c.id}/cronograma`}
                            className="bg-surface border border-border/60 rounded-lg px-4 py-3 flex items-center justify-between hover:border-primary/40 transition"
                          >
                            <div className="min-w-0 flex-1">
                              <div className="text-sm font-medium text-fg truncate">{c.nome}</div>
                              {c.pasta && (
                                <div className="text-xs text-fg-faint truncate">{c.pasta}</div>
                              )}
                            </div>
                            <span className="text-fg-faint text-xs shrink-0 ml-4 whitespace-nowrap">
                              {c.total.toLocaleString("pt-BR")} questões · criar →
                            </span>
                          </a>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </>
            )}
          </section>
        )}
      </main>
    </div>
  );
}

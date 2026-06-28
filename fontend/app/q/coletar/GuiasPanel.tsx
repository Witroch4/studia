"use client";

import { useState } from "react";
import Link from "next/link";
import { apiFetch, apiJson } from "@/lib/api";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { qk } from "@/lib/queryKeys";

interface GuiaCard {
  id: number;
  nome: string;
  banca: string | null;
  status: string;
  cadernos_total: number;
  questoes_esperadas: number;
  questoes_coletadas: number;
  cadernos_materializados: number;
  coleta_completa: boolean;
  pct: number;
}

interface BuscaGuia {
  slug: string;
  url: string;
  ano: number | null;
  orgao: string | null;
  banca: string | null;
  data_prova: string | null;
  guia_id: number | null;
}

interface GuiasResponse {
  guias: GuiaCard[];
}

interface FilaItem {
  id: number;
  url: string | null;
  status: string;
  guia_id: number | null;
  guia_nome: string | null;
  posicao: number | null;
  erro: string | null;
}

interface FilaResp {
  fila: FilaItem[];
  ativo: boolean;
  proximo_em_segundos: number;
}

const FILA_TERMINAL = ["done", "skipped", "error"];

// Estado de exibição derivado: a coluna `status` do banco só vira "done" depois
// que o usuário materializa ("Salvar"). Enquanto isso, se todos os jobs de
// coleta terminaram (`coleta_completa`), a coleta acabou — o que o TC tinha já
// veio. Nesse caso mostramos "Coletado" (pronto pra montar), não "Coletando",
// pra bater com a tela de detalhe do guia, que já marca cada caderno COLETADO.
type EstadoGuia = "coletando" | "coletado" | "concluido" | "salvando" | "erro";

function estadoGuia(g: GuiaCard): EstadoGuia {
  if (g.status === "error") return "erro";
  if (g.status === "done") return "concluido";
  if (g.status === "saving") return "salvando";
  if (g.coleta_completa) return "coletado";
  return "coletando";
}

const ESTADO_LABEL: Record<EstadoGuia, string> = {
  coletando: "Coletando",
  coletado: "Coletado",
  concluido: "Concluído",
  salvando: "Salvando",
  erro: "Erro",
};

function estadoBadge(e: EstadoGuia): string {
  if (e === "concluido") return "bg-success/15 text-success border-success/40";
  if (e === "coletado") return "bg-success/15 text-success border-success/40";
  if (e === "coletando" || e === "salvando") return "bg-primary/15 text-primary border-primary/40";
  if (e === "erro") return "bg-error/15 text-error border-error/40";
  return "bg-surface-2 text-fg border-border";
}

/**
 * Painel de Guias embutido na página Coleta TC — concentra num só lugar a
 * coleta de guias (cadernos+questões) e o acompanhamento. A coleta de cada
 * caderno do guia reusa a mesma fila TaskIQ exibida abaixo em "Jobs ativos".
 */
export default function GuiasPanel() {
  const queryClient = useQueryClient();
  const [urls, setUrls] = useState("");
  const [importando, setImportando] = useState(false);
  const [importandoSlug, setImportandoSlug] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  const [termo, setTermo] = useState("");
  const [buscando, setBuscando] = useState(false);
  const [resultados, setResultados] = useState<BuscaGuia[]>([]);

  const [montandoId, setMontandoId] = useState<number | null>(null);

  // Poll while any guia is still being collected (not yet coleta_completa).
  const { data: guiasData, error: guiasError } = useQuery<GuiasResponse>({
    queryKey: qk.guias(),
    queryFn: () => apiJson<GuiasResponse>("/api/q/guias"),
    refetchInterval: (q) => {
      const guias = q.state.data?.guias ?? [];
      const hasActive = guias.some((g) => !g.coleta_completa && g.status !== "done" && g.status !== "error");
      return hasActive ? 15000 : false;
    },
  });

  const erroGuias = guiasError ? (guiasError as Error).message : null;

  const guias: GuiaCard[] = guiasData?.guias ?? [];

  // Fila de coleta: poll enquanto houver entrada não-terminal (coletando/queued).
  const { data: filaData } = useQuery<FilaResp>({
    queryKey: qk.guiaFila(),
    queryFn: () => apiJson<FilaResp>("/api/q/guias/fila"),
    refetchInterval: (q) => {
      const naoTerminal = (q.state.data?.fila ?? []).some(
        (e) => !FILA_TERMINAL.includes(e.status),
      );
      return naoTerminal ? 15000 : false;
    },
  });
  const fila: FilaItem[] = filaData?.fila ?? [];

  async function removerFila(id: number) {
    await apiFetch(`/api/q/guias/fila/${id}`, { method: "DELETE" });
    await queryClient.invalidateQueries({ queryKey: qk.guiaFila() });
  }

  async function pularFila(id: number) {
    await apiFetch(`/api/q/guias/fila/${id}/pular`, { method: "POST" });
    await queryClient.invalidateQueries({ queryKey: qk.guiaFila() });
  }

  async function montarGuia(guiaId: number) {
    setMontandoId(guiaId);
    setMsg(null);
    try {
      const r = await apiFetch(`/api/q/guias/${guiaId}/materializar`, {
        method: "POST",
      });
      const data = await r.json().catch(() => null);
      if (!r.ok) setMsg(data?.detail || `Falha ao salvar (HTTP ${r.status})`);
      else {
        setMsg(`✓ ${data?.total ?? 0} caderno(s) salvos para estudo.`);
        await queryClient.invalidateQueries({ queryKey: qk.guias() });
      }
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setMontandoId(null);
    }
  }

  // Adiciona uma ou mais URLs (uma por linha) à fila de coleta serial.
  async function importarLote() {
    const lista = urls
      .split("\n")
      .map((u) => u.trim())
      .filter(Boolean);
    if (lista.length === 0) {
      setMsg("Cole uma ou mais URLs de guias (uma por linha).");
      return;
    }
    setImportando(true);
    setMsg(null);
    try {
      const r = await apiFetch("/api/q/guias/importar-lote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls: lista }),
      });
      const data = await r.json();
      if (!r.ok) setMsg(data.detail || data.message || `HTTP ${r.status}`);
      else {
        setMsg(`✓ ${data.enfileirados} guia(s) adicionados à fila de coleta.`);
        setUrls("");
        await queryClient.invalidateQueries({ queryKey: qk.guiaFila() });
        await queryClient.invalidateQueries({ queryKey: qk.guias() });
      }
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setImportando(false);
    }
  }

  // Importar 1 guia (resultado da busca) → também entra na fila de coleta.
  async function importar(targetUrl: string, slug?: string) {
    if (!targetUrl.trim()) return;
    if (slug) setImportandoSlug(slug);
    setMsg(null);
    try {
      const r = await apiFetch("/api/q/guias/importar-lote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls: [targetUrl.trim()] }),
      });
      const data = await r.json();
      if (!r.ok) setMsg(data.detail || data.message || `HTTP ${r.status}`);
      else {
        setMsg(`✓ ${data.enfileirados} guia(s) na fila de coleta.`);
        await queryClient.invalidateQueries({ queryKey: qk.guiaFila() });
        if (termo) void buscar();
      }
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setImportandoSlug(null);
    }
  }

  // buscar-tc é uma ação de pesquisa pontual (não polling) — mantém como fetch manual.
  async function buscar() {
    if (!termo.trim()) return;
    setBuscando(true);
    try {
      const r = await apiFetch(`/api/q/guias/buscar-tc?termo=${encodeURIComponent(termo.trim())}`, {
        cache: "no-store",
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setResultados(Array.isArray(data.guias) ? data.guias : []);
    } catch (e) {
      setMsg((e as Error).message);
    } finally {
      setBuscando(false);
    }
  }

  return (
    <section className="border border-border rounded-lg bg-page/70 p-4 space-y-4">
      <div>
        <h2 className="text-sm font-semibold text-fg-strong flex items-center gap-2">
          <span className="material-symbols-outlined text-primary text-[18px]">menu_book</span>
          Guias de estudo
        </h2>
        <p className="text-xs text-fg-faint mt-1">
          Importe um guia inteiro do TC pela URL base. Cada caderro do guia é coletado
          pela mesma fila abaixo, e vira um caderno de estudo por matéria.
        </p>
      </div>

      {/* Importar em lote por URLs */}
      <div className="flex flex-col gap-2">
        <textarea
          value={urls}
          onChange={(e) => setUrls(e.target.value)}
          placeholder={"Cole uma ou mais URLs de guias (uma por linha)\nhttps://www.tecconcursos.com.br/guias/oab-2026\nhttps://www.tecconcursos.com.br/guias/..."}
          rows={4}
          className="px-3 py-2 bg-surface-2 border border-border rounded text-sm focus:outline-none focus:border-primary font-mono"
          disabled={importando}
        />
        <button
          onClick={() => void importarLote()}
          disabled={importando}
          className="self-start bg-cyan-600 hover:bg-cyan-500 disabled:bg-surface-2 px-4 py-2 rounded text-sm font-semibold"
        >
          {importando ? "Adicionando…" : "Adicionar à fila de coleta"}
        </button>
        <p className="text-xs text-fg-faint">
          Os guias são coletados <strong>1 por vez</strong>, com pausa de ~15 min entre eles
          para não sobrecarregar o TC — vale igual colando todas de uma vez ou uma a uma.
        </p>
      </div>

      {/* Buscar guias no TC */}
      <div className="flex flex-col md:flex-row gap-2">
        <input
          type="text"
          value={termo}
          onChange={(e) => setTermo(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && void buscar()}
          placeholder="Buscar guias no TC (ex.: oab, sefaz, trt)"
          className="flex-1 px-3 py-2 bg-surface-2 border border-border rounded text-sm focus:outline-none focus:border-primary"
          disabled={buscando}
        />
        <button
          onClick={() => void buscar()}
          disabled={buscando || !termo.trim()}
          className="bg-surface-2 hover:bg-fg-strong/6 disabled:opacity-60 px-4 py-2 rounded text-sm font-semibold whitespace-nowrap"
        >
          {buscando ? "Buscando…" : "Buscar"}
        </button>
      </div>

      {resultados.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {resultados.map((g) => (
            <div key={g.slug} className="rounded border border-border bg-black/30 p-2 flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm text-fg truncate">{g.orgao} {g.ano}</div>
                <div className="text-xs text-fg-faint truncate">
                  {g.banca}{g.data_prova ? ` · prova ${g.data_prova.slice(0, 10)}` : ""}
                </div>
              </div>
              {g.guia_id ? (
                <Link href={`/q/guias/${g.guia_id}`} className="text-xs bg-success/15 text-success border border-success/40 px-2 py-1 rounded whitespace-nowrap">
                  Importado →
                </Link>
              ) : (
                <button
                  onClick={() => void importar(g.url, g.slug)}
                  disabled={importandoSlug === g.slug}
                  className="text-xs bg-cyan-600 hover:bg-cyan-500 disabled:bg-surface-2 px-2 py-1 rounded font-semibold whitespace-nowrap"
                >
                  {importandoSlug === g.slug ? "…" : "Importar"}
                </button>
              )}
            </div>
          ))}
        </div>
      )}

      {msg && <div className="text-xs text-primary">{msg}</div>}
      {erroGuias && <div className="text-xs text-error">Falha ao listar guias: {erroGuias}</div>}

      {/* Fila de coleta */}
      {fila.length > 0 && (
        <div className="space-y-2 pt-1">
          <div className="flex items-center justify-between">
            <div className="text-xs text-fg-faint uppercase tracking-wide">Fila de coleta</div>
            {!filaData?.ativo && (filaData?.proximo_em_segundos ?? 0) > 0 && (
              <span className="text-[11px] text-amber-400">
                Esfriando — próximo guia em ~{Math.ceil((filaData!.proximo_em_segundos) / 60)} min
              </span>
            )}
          </div>
          {fila.map((e) => {
            const label =
              e.status === "collecting" ? "Coletando"
              : e.status === "resolving" ? "Resolvendo"
              : e.status === "queued" ? `Na fila${e.posicao ? ` #${e.posicao}` : ""}`
              : e.status === "done" ? "Concluído"
              : e.status === "skipped" ? "Pulado"
              : "Erro";
            const cor =
              e.status === "collecting" || e.status === "resolving" ? "text-primary border-primary/40 bg-primary/15"
              : e.status === "done" ? "text-success border-success/40 bg-success/15"
              : e.status === "error" ? "text-error border-error/40 bg-error/15"
              : "text-fg border-border bg-surface-2";
            return (
              <div key={e.id} className="rounded border border-border bg-black/20 p-2 flex items-center justify-between gap-2">
                <div className="min-w-0">
                  {e.guia_id ? (
                    <Link href={`/q/guias/${e.guia_id}`} className="text-sm text-fg truncate hover:text-primary">
                      {e.guia_nome || e.url || `Guia ${e.guia_id}`}
                    </Link>
                  ) : (
                    <div className="text-sm text-fg truncate">{e.url || `Guia ${e.id}`}</div>
                  )}
                  {e.erro && <div className="text-[11px] text-error truncate">{e.erro}</div>}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded border ${cor}`}>{label}</span>
                  {e.status === "queued" && (
                    <button
                      onClick={() => void removerFila(e.id)}
                      aria-label="Remover da fila"
                      title="Remover da fila"
                      className="text-xs text-fg-faint hover:text-error px-1"
                    >
                      ✕
                    </button>
                  )}
                  {(e.status === "collecting" || e.status === "resolving") && (
                    <button
                      onClick={() => void pularFila(e.id)}
                      title="Pular guia"
                      className="text-xs text-amber-400 hover:text-amber-300 px-1"
                    >
                      Pular
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Guias importados */}
      {guias.length > 0 && (
        <div className="space-y-2 pt-1">
          <div className="text-xs text-fg-faint uppercase tracking-wide">Guias importados</div>
          {guias.map((g) => {
            const estado = estadoGuia(g);
            // Coleta terminou ⇒ barra cheia: o que o TC tinha já veio (o
            // "esperado" do guia é inflado e nem sempre existe na origem).
            const larguraBarra = estado === "coletado" || estado === "concluido" ? 100 : Math.min(100, g.pct);
            const faltaMontar = g.coleta_completa && g.cadernos_materializados < g.cadernos_total;
            return (
              <div
                key={g.id}
                className="rounded border border-border bg-black/20 hover:border-primary/40 p-3"
              >
                <Link href={`/q/guias/${g.id}`} className="block">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-sm font-medium text-fg-strong truncate">{g.nome}</div>
                    <span className={`text-[10px] uppercase font-semibold px-2 py-0.5 rounded border ${estadoBadge(estado)}`}>
                      {ESTADO_LABEL[estado]}
                    </span>
                  </div>
                  <div className="mt-1 text-xs text-fg-muted">
                    {g.questoes_coletadas.toLocaleString("pt-BR")} questões ·{" "}
                    {g.cadernos_materializados}/{g.cadernos_total} cadernos salvos para estudo
                  </div>
                  <div className="h-1.5 rounded-full bg-surface-2 overflow-hidden mt-2">
                    <div className="h-full bg-cyan-500 transition-all" style={{ width: `${larguraBarra}%` }} />
                  </div>
                </Link>
                {faltaMontar && (
                  <div className="mt-2 flex items-center justify-between gap-2">
                    <span className="text-[11px] text-success">Coleta concluída — salve para liberar o estudo.</span>
                    <button
                      onClick={() => void montarGuia(g.id)}
                      disabled={montandoId === g.id}
                      className="text-xs bg-cyan-600 hover:bg-cyan-500 disabled:bg-surface-2 px-3 py-1 rounded font-semibold whitespace-nowrap"
                    >
                      {montandoId === g.id ? "Salvando…" : "Salvar todos os cadernos"}
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}

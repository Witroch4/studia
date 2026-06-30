"use client";

import { Suspense, useState, useEffect } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiJson } from "@/lib/api";
import { authClient } from "@/lib/auth-client";
import { qk } from "@/lib/queryKeys";
import { toast } from "sonner";
import { PromptDialog } from "@/app/components/PromptDialog";

/**
 * /q/cadernos — "Minhas pastas", hierarquia estilo TecConcursos:
 *   Estudo › Minhas pastas               → lista de pastas
 *   Estudo › Minhas pastas › {pasta}     → cadernos da pasta (?pasta=Nome)
 *
 * Pasta vem por query string (não rota dinâmica) porque nomes de pasta
 * contêm "/" (ex: "Guia OAB / 2026 …"). `?pasta=` (vazio) = sem classificação.
 */

const SEM_CLASSIFICACAO = "Sem classificação";

interface PastaRow {
  pasta: string | null;
  cadernos: number;
  total_questoes: number;
}

interface CadernoRow {
  id: number;
  nome: string;
  total: number;
  pasta: string | null;
  created_at: string | null;
}

interface Desempenho {
  resolvidas: number;
  acertos: number;
  erros: number;
}

function iniciaisPasta(nome: string): string {
  const palavras = nome.replace(/[^\p{L}\p{N} ]/gu, " ").split(/\s+/).filter(Boolean);
  return palavras.slice(0, 2).map((p) => p[0]).join("").toUpperCase() || "📁";
}

function PastasView({ pastas }: { pastas: PastaRow[] }) {
  const router = useRouter();
  return (
    <div className="space-y-3">
      {pastas.length === 0 && (
        <p className="text-sm text-fg-faint italic">
          Nenhum caderno criado ainda. Use <Link href="/q/filtrar" className="text-primary hover:underline">Filtrar Questões</Link>{" "}
          ou monte por um <Link href="/q/guias" className="text-primary hover:underline">Guia de Estudos</Link>.
        </p>
      )}
      {pastas.map((p) => {
        const nome = p.pasta ?? SEM_CLASSIFICACAO;
        const href = `/q/cadernos?pasta=${encodeURIComponent(p.pasta ?? "")}`;
        return (
          <div
            key={nome}
            onClick={() => router.push(href)}
            className="flex items-center gap-4 p-4 rounded-lg border border-border/60 bg-surface hover:border-primary/40 cursor-pointer transition"
          >
            <div className="w-11 h-11 rounded-full bg-gradient-to-br from-cyan-600 to-violet-600 flex items-center justify-center text-sm font-bold shrink-0">
              {p.pasta ? iniciaisPasta(p.pasta) : "📁"}
            </div>
            <div className="flex-1 min-w-0">
              <Link href={href} onClick={(e) => e.stopPropagation()} className="font-semibold text-primary hover:underline truncate block">
                {nome}
              </Link>
              <div className="text-xs text-fg-faint">{p.total_questoes.toLocaleString("pt-BR")} questões</div>
            </div>
            <div className="text-sm text-fg-muted shrink-0">{p.cadernos} caderno{p.cadernos === 1 ? "" : "s"}</div>
          </div>
        );
      })}
    </div>
  );
}

function CadernosView({ pasta }: { pasta: string }) {
  const queryClient = useQueryClient();
  const [desempenho, setDesempenho] = useState<Record<number, Desempenho | "loading">>({});
  const [importando, setImportando] = useState<Record<number, boolean>>({});
  const [coletandoComents, setColetandoComents] = useState<Record<number, boolean>>({});
  const [editando, setEditando] = useState<{ id: number; nome: string } | null>(null);
  const [ehAdmin, setEhAdmin] = useState(false);
  const [promptGabarito, setPromptGabarito] = useState<{ aberto: boolean; cadernoId: number | null }>({ aberto: false, cadernoId: null });

  useEffect(() => {
    authClient
      .getSession()
      .then((res) => {
        const role = (res?.data?.user as { role?: string } | undefined)?.role;
        setEhAdmin(role === "admin");
      })
      .catch(() => {});
  }, []);

  const { data: cadernos, isPending } = useQuery({
    queryKey: qk.cadernos(pasta),
    queryFn: () => apiJson<CadernoRow[]>(`/api/q/cadernos?pasta=${encodeURIComponent(pasta)}`),
  });

  const renomear = useMutation({
    mutationFn: ({ id, nome }: { id: number; nome: string }) =>
      apiJson<{ id: number; nome: string }>(`/api/q/cadernos/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nome }),
      }),
    onSuccess: (data) => {
      setEditando(null);
      // Atualiza a lista local imediatamente e revalida o detalhe.
      queryClient.setQueryData<CadernoRow[]>(qk.cadernos(pasta), (old) =>
        old?.map((c) => (c.id === data.id ? { ...c, nome: data.nome } : c)),
      );
      queryClient.invalidateQueries({ queryKey: qk.caderno(data.id) });
    },
  });

  function salvarEdicao() {
    if (!editando) return;
    const nome = editando.nome.trim();
    if (!nome) return;
    renomear.mutate({ id: editando.id, nome });
  }

  async function carregarDesempenho(id: number) {
    setDesempenho((d) => ({ ...d, [id]: "loading" }));
    try {
      const r = await apiFetch(`/api/q/cadernos/${id}/estatisticas`);
      const data = await r.json();
      setDesempenho((d) => ({ ...d, [id]: { resolvidas: data.resolvidas, acertos: data.acertos, erros: data.erros } }));
    } catch (e) {
      console.error(e);
      setDesempenho((d) => {
        const resto = { ...d };
        delete resto[id];
        return resto;
      });
    }
  }

  async function importarComentarios(id: number) {
    setColetandoComents((s) => ({ ...s, [id]: true }));
    try {
      const r = await apiFetch(`/api/q/cadernos/${id}/importar-comentarios-tc`, {
        method: "POST",
      });
      if (!r.ok) {
        const erro = await r.json().catch(() => ({}));
        throw new Error((erro as { detail?: string }).detail || `falha ${r.status}`);
      }
      toast.success("Coleta iniciada em background — acompanhe em Coletar.");
    } catch (e) {
      console.error(e);
      toast.error(`Não foi possível iniciar a coleta: ${e instanceof Error ? e.message : e}`);
    } finally {
      setColetandoComents((s) => ({ ...s, [id]: false }));
    }
  }

  function abrirPromptGabarito(id: number) {
    setPromptGabarito({ aberto: true, cadernoId: id });
  }

  async function confirmarImportarGabarito(entrada: string) {
    const id = promptGabarito.cadernoId;
    setPromptGabarito({ aberto: false, cadernoId: null });
    if (id === null) return;
    const texto = entrada.trim();
    const pareceTabela = /#\d{4,}/.test(texto) && /(Acertou|Errou|Não resolvida|Anulada)/i.test(texto);
    const m = pareceTabela ? null : texto.match(/(\d{4,})/);
    const tc_caderno_id = m ? Number(m[1]) : null;

    setImportando((s) => ({ ...s, [id]: true }));
    try {
      const r = await apiFetch(`/api/q/cadernos/${id}/importar-gabarito`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(
          pareceTabela
            ? { texto_estatistica: texto, sobrescrever: true }
            : { tc_caderno_id, sobrescrever: true },
        ),
      });
      if (!r.ok) {
        const erro = await r.json().catch(() => ({}));
        throw new Error(erro.detail || `falha ${r.status}`);
      }
      const res = await r.json();
      setDesempenho((d) => ({
        ...d,
        [id]: { resolvidas: res.resolvidas, acertos: res.acertos, erros: res.erros },
      }));
      toast.success(
        `Desempenho importado: ${res.resolvidas} resolvidas (${res.acertos} acertos, ${res.erros} erros)` +
          ` · ${res.importadas} novas` +
          (res.atualizadas ? ` · ${res.atualizadas} atualizadas` : "") +
          ` · ${res.ja_tinha} já existiam` +
          ` · ${res.nao_resolvidas_no_tec} ainda não resolvidas` +
          (res.anuladas_no_tec ? ` · ${res.anuladas_no_tec} anuladas` : "") +
          (res.nao_mapeadas
            ? ` · ${res.nao_mapeadas} questões não encontradas (caderno coletado parcialmente)`
            : ""),
      );
    } catch (e) {
      console.error(e);
      toast.error(`Não foi possível importar: ${e instanceof Error ? e.message : e}`);
    } finally {
      setImportando((s) => ({ ...s, [id]: false }));
    }
  }

  if (isPending && !cadernos) return <p className="text-sm text-fg-faint">Carregando…</p>;
  if (!cadernos || cadernos.length === 0) return <p className="text-sm text-fg-faint italic">Nenhum caderno nesta pasta.</p>;

  return (
    <>
    <div className="space-y-2">
      {cadernos.map((c: CadernoRow) => {
        const d = desempenho[c.id];
        return (
          <div
            key={c.id}
            className="group flex items-center gap-4 px-4 py-3 rounded-lg border border-border/60 bg-surface hover:border-primary/40 transition"
          >
            <span className="text-fg-faint">🎓</span>
            <div className="flex-1 min-w-0">
              {editando?.id === c.id ? (
                <input
                  autoFocus
                  value={editando.nome}
                  onChange={(e) => setEditando({ id: c.id, nome: e.target.value })}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") salvarEdicao();
                    if (e.key === "Escape") setEditando(null);
                  }}
                  onBlur={() => salvarEdicao()}
                  disabled={renomear.isPending}
                  className="w-full bg-page border border-primary/50 rounded px-2 py-1 text-sm font-medium text-fg focus:outline-none focus:border-primary"
                />
              ) : (
                <div className="flex items-center gap-2 min-w-0">
                  <Link
                    href={`/q/caderno/${c.id}`}
                    className="text-sm font-medium text-fg hover:text-primary hover:underline truncate block"
                    onMouseEnter={() => queryClient.prefetchQuery({
                      queryKey: qk.caderno(c.id),
                      queryFn: () => apiJson(`/api/q/cadernos/${c.id}`),
                      staleTime: 30_000,
                    })}
                    onFocus={() => queryClient.prefetchQuery({
                      queryKey: qk.caderno(c.id),
                      queryFn: () => apiJson(`/api/q/cadernos/${c.id}`),
                      staleTime: 30_000,
                    })}
                  >
                    {c.nome}
                  </Link>
                  <button
                    type="button"
                    title="Renomear caderno"
                    aria-label="Renomear caderno"
                    onClick={() => setEditando({ id: c.id, nome: c.nome })}
                    className="shrink-0 text-fg-faint hover:text-primary opacity-0 group-hover:opacity-100 focus:opacity-100 transition"
                  >
                    <span className="material-symbols-outlined text-[18px] leading-none align-middle">edit</span>
                  </button>
                </div>
              )}
              <div className="text-xs text-fg-faint">
                {c.total.toLocaleString("pt-BR")} questões
                {c.created_at && <> · criado em {new Date(c.created_at).toLocaleDateString("pt-BR")}</>}
              </div>
            </div>
            <div className="flex items-center gap-3 text-xs shrink-0">
              {!d && (
                <button onClick={() => carregarDesempenho(c.id)} className="text-primary hover:underline">
                  Carregar desempenho
                </button>
              )}
              {d === "loading" && <span className="text-fg-faint">…</span>}
              {d && d !== "loading" && (
                <span className="text-fg-muted">
                  {d.resolvidas} resolvidas · <span className="text-success">{d.acertos} acertos</span> ·{" "}
                  <span className="text-error">{d.erros} erros</span>
                </span>
              )}
              <button
                onClick={() => abrirPromptGabarito(c.id)}
                disabled={importando[c.id]}
                title="Importar acertos/erros do desempenho"
                className="text-fg-faint hover:text-primary disabled:opacity-50 opacity-0 group-hover:opacity-100 focus:opacity-100 transition whitespace-nowrap"
              >
                {importando[c.id] ? "importando…" : "↓ Desempenho"}
              </button>
              {ehAdmin && (
                <button
                  onClick={() => importarComentarios(c.id)}
                  disabled={coletandoComents[c.id]}
                  title="Importar comentários"
                  className="text-fg-faint hover:text-primary disabled:opacity-50 opacity-0 group-hover:opacity-100 focus:opacity-100 transition whitespace-nowrap"
                >
                  {coletandoComents[c.id] ? "coletando…" : "💬 Importar"}
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
    <PromptDialog
      key={promptGabarito.cadernoId ?? "closed"}
      open={promptGabarito.aberto}
      titulo="Importar desempenho"
      descricao="Cole a URL/ID do caderno de origem ou a tabela copiada da aba de desempenho."
      placeholder={"https://… ou 12345\n\nOu cole a tabela com Nº, Status, Resolvida em e Código."}
      multiline
      onConfirm={confirmarImportarGabarito}
      onCancel={() => setPromptGabarito({ aberto: false, cadernoId: null })}
    />
    </>
  );
}

function MinhasPastasInner() {
  const searchParams = useSearchParams();
  const pastaParam = searchParams.has("pasta") ? (searchParams.get("pasta") ?? "") : null;

  const { data: pastas = [], isPending: pastasPending } = useQuery({
    queryKey: qk.pastas(),
    queryFn: () => apiJson<PastaRow[]>("/api/q/pastas"),
  });

  const tituloPasta = pastaParam === null ? null : pastaParam === "" ? SEM_CLASSIFICACAO : pastaParam;

  return (
    <div className="min-h-screen bg-page text-fg">
      <div className="border-b border-border/60 px-6 py-2 flex items-center gap-3 text-xs bg-page">
        <span className="text-fg-faint">Estudo</span>
        <span className="text-fg-faint">›</span>
        {tituloPasta === null ? (
          <span className="text-fg-muted">Minhas pastas</span>
        ) : (
          <>
            <Link href="/q/cadernos" className="text-fg-faint hover:text-primary hover:underline">Minhas pastas</Link>
            <span className="text-fg-faint">›</span>
            <span className="text-fg-muted truncate max-w-[50vw]">{tituloPasta}</span>
          </>
        )}
      </div>

      <main className="max-w-4xl mx-auto px-6 py-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold">{tituloPasta ?? "Minhas pastas"}</h1>
          <Link
            href="/q/filtrar"
            className="bg-cyan-600 hover:bg-cyan-500 px-4 py-2 rounded text-sm font-semibold"
          >
            NOVO CADERNO
          </Link>
        </div>

        {pastaParam === null ? (
          pastasPending && pastas.length === 0 ? (
            <p className="text-sm text-fg-faint">Carregando…</p>
          ) : (
            <PastasView pastas={pastas} />
          )
        ) : (
          <CadernosView pasta={pastaParam} />
        )}
      </main>
    </div>
  );
}

export default function MinhasPastasPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-page" />}>
      <MinhasPastasInner />
    </Suspense>
  );
}

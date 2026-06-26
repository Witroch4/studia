"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient, keepPreviousData } from "@tanstack/react-query";
import { useHotkeys, ATALHOS_TC } from "../../../hooks/useHotkeys";
import type { CanvasTool, StrikeTarget } from "./annotations/types";
import { useQuestionAnnotations } from "./annotations/useQuestionAnnotations";
import { CanvasToolbar } from "./components/CanvasToolbar";
import { QuestionCanvasOverlay } from "./components/QuestionCanvasOverlay";
import { ScientificCalculator } from "./components/ScientificCalculator";
import { StrikableAlternative } from "./components/StrikableAlternative";
import QuestionHtml from "../../../components/QuestionHtml";
import { ForumPanel } from "./components/ForumPanel";
import { apiFetch, apiJson, apiPost } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

interface Alternativa {
  id: number;
  letra: string;
  texto_md: string;
  texto_html: string | null;
  correta: boolean | null;
  ordem: number;
}

interface Questao {
  id: number;
  id_externo: number;
  enunciado_html: string;
  gabarito: string;
  status: string;
  tipo: string;
  banca: { sigla: string; nome: string } | null;
  orgao: { sigla: string; nome: string } | null;
  cargo: { nome: string; ano: number } | null;
  materia: { id: number; nome: string } | null;
  assuntos: { id: number; nome: string }[];
  alternativas: Alternativa[];
  forum_count?: number;
}

interface Caderno {
  id: number;
  nome: string;
  pasta: string | null;
  total: number;
  question_ids: number[];
}

interface Stats {
  resolvidas: number;
  acertos: number;
  erros: number;
}

type Tab = "Questoes" | "Indice" | "Estatisticas" | "Gabarito" | "Configuracoes" | "Imprimir";

function formatTempo(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export default function CadernoPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const queryClient = useQueryClient();

  // ─── UI state (preserved 100%) ───
  const [idx, setIdx] = useState(0);
  // Resposta vinculada à questão atual: ao trocar de qid o estado é descartado sem useEffect
  const [respostaQid, setRespostaQid] = useState<number | null>(null);
  const [respostaState, setRespostaState] = useState<{
    selecionada: string | null;
    resolvida: boolean;
    acertou: boolean | null;
  }>({ selecionada: null, resolvida: false, acertou: null });
  const [showAtalhos, setShowAtalhos] = useState(false);
  const [gotoOpen, setGotoOpen] = useState(false);
  const [gotoValue, setGotoValue] = useState("");
  const [fontSize, setFontSize] = useState(16);
  const [tab, setTab] = useState<Tab>("Questoes");
  const [tempo, setTempo] = useState(0);
  const [pausado, setPausado] = useState(false);
  const [canvasActive, setCanvasActive] = useState(false);
  const [canvasTool, setCanvasTool] = useState<CanvasTool>("pen");
  const [canvasColor, setCanvasColor] = useState("#22c55e");
  const [canvasWidth, setCanvasWidth] = useState(5);
  const [calculatorOpen, setCalculatorOpen] = useState(false);
  const [forumAberto, setForumAberto] = useState(false);
  const [paywall, setPaywall] = useState<string | null>(null);
  // limite local: sobrescrito pelo retorno do /responder, sincronizado com a query
  const [limiteLocal, setLimiteLocal] = useState<{
    usado: number; limite: number; restantes: number | null; ilimitado: boolean;
  } | null>(null);
  const questionCardRef = useRef<HTMLDivElement | null>(null);
  const startedAt = useRef<number>(0);

  // ─── Timer global (preservado) ───
  useEffect(() => {
    startedAt.current = Date.now();
  }, []);

  useEffect(() => {
    if (pausado) return;
    const t = setInterval(() => setTempo((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, [pausado]);

  // ─── Caderno (skeleton só aqui) ───
  const { data: caderno, isPending: cadernoLoading } = useQuery<Caderno>({
    queryKey: qk.caderno(id),
    queryFn: () => apiJson(`/api/q/cadernos/${id}`),
    staleTime: 5 * 60 * 1000,
  });

  // ─── Stats do caderno ───
  const { data: statsData } = useQuery<Stats>({
    queryKey: qk.cadernoSub(id, "estatisticas"),
    queryFn: () => apiJson(`/api/q/cadernos/${id}/estatisticas`),
    enabled: !!caderno,
    staleTime: 30_000,
  });
  const stats: Stats = statsData ?? { resolvidas: 0, acertos: 0, erros: 0 };

  // Derivar caderno direto pelo cabeçalho da questão (Resolvidas/Acertos/Erros).
  const { abrirDialog: derivarCaderno, modais: derivarModais } = useDerivarCaderno(
    caderno?.id ?? 0,
    caderno?.nome ?? "",
  );

  // ─── Limite diário ───
  const { data: limiteQuery } = useQuery<{
    usado: number; limite: number; restantes: number | null; ilimitado: boolean;
  }>({
    queryKey: qk.limite(),
    queryFn: () => apiJson("/api/q/limite"),
    staleTime: 60_000,
  });
  // O /responder retorna limite atualizado — usamos o valor local se presente (mais fresco)
  const limite = limiteLocal ?? limiteQuery ?? null;

  // ─── Favoritas ───
  const { data: favData } = useQuery<{ ids: number[] }>({
    queryKey: qk.favoritas(),
    queryFn: () => apiJson("/api/q/favoritas"),
    staleTime: 5 * 60 * 1000,
  });
  const favIds = new Set<number>(favData?.ids ?? []);

  // ─── Minhas resoluções neste caderno (trava as já respondidas) ───
  const { data: minhasResData } = useQuery<{
    resolucoes: Record<string, { resposta: string | null; acertou: boolean | null }>;
  }>({
    queryKey: qk.cadernoSub(id, "minhas-resolucoes"),
    queryFn: () => apiJson(`/api/q/cadernos/${id}/minhas-resolucoes`),
    enabled: !!caderno,
    staleTime: 30_000,
  });
  const minhasResolucoes = minhasResData?.resolucoes ?? {};
  const resolvidasSet = new Set<number>(Object.keys(minhasResolucoes).map(Number));

  const currentQid = caderno?.question_ids[idx];
  const fav = currentQid ? favIds.has(currentQid) : false;

  // Deriva o estado de resposta: estado local (resposta recém-enviada) tem
  // prioridade; senão, se o servidor diz que já resolvi esta questão neste
  // caderno, restaura travado (gabarito visível); senão, questão nova.
  const respostaServidor =
    currentQid != null ? minhasResolucoes[String(currentQid)] : undefined;
  const respostaAtual =
    respostaQid === (currentQid ?? null)
      ? respostaState
      : respostaServidor
        ? { selecionada: respostaServidor.resposta, resolvida: true, acertou: respostaServidor.acertou }
        : { selecionada: null, resolvida: false, acertou: null };
  const { selecionada, resolvida, acertou } = respostaAtual;

  // ─── Questão atual (keepPreviousData: sem skeleton ao trocar de questão) ───
  const { data: questao } = useQuery<Questao>({
    queryKey: qk.questao(currentQid ?? 0),
    queryFn: () => apiJson(`/api/q/${currentQid}`),
    enabled: !!currentQid,
    placeholderData: keepPreviousData,
    staleTime: 10 * 60 * 1000,
  });

  // ─── Prefetch inteligente: aquece o cache das próximas prováveis ───
  // Mata a "engasgada" ao navegar: → ← N (vizinhos) e L (pool aleatório de
  // não resolvidas) já vêm do cache. prefetchQuery é no-op se já estiver fresco.
  useEffect(() => {
    if (!caderno) return;
    const ids = caderno.question_ids;
    const warm = (qid?: number) => {
      if (qid == null) return;
      void queryClient.prefetchQuery({
        queryKey: qk.questao(qid),
        queryFn: () => apiJson(`/api/q/${qid}`),
        staleTime: 10 * 60 * 1000,
      });
    };
    warm(ids[idx + 1]);
    warm(ids[idx + 2]);
    warm(ids[idx - 1]);
    const resolvidas = new Set(Object.keys(minhasResData?.resolucoes ?? {}).map(Number));
    const naoResolvidas = ids.filter((qid, i) => i !== idx && !resolvidas.has(qid));
    const alvo = Math.min(5, naoResolvidas.length);
    const escolhidas = new Set<number>();
    let tentativas = 0;
    while (escolhidas.size < alvo && tentativas < alvo * 4) {
      escolhidas.add(naoResolvidas[Math.floor(Math.random() * naoResolvidas.length)]);
      tentativas++;
    }
    escolhidas.forEach(warm);
  }, [caderno, idx, minhasResData, queryClient]);

  // ─── Mutation: responder questão ───
  const responderMutation = useMutation({
    mutationFn: async ({
      qid,
      resposta,
      tempo_segundos,
      caderno_id,
    }: {
      qid: number;
      resposta: string;
      tempo_segundos: number;
      caderno_id: number;
    }) => {
      const r = await apiFetch(`/api/q/${qid}/responder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resposta, tempo_segundos, caderno_id }),
      });
      if (r.status === 402) {
        const err = await r.json().catch(() => null);
        // Lança erro especial para ser capturado no onError
        throw Object.assign(new Error("paywall"), { isPaywall: true, detail: err });
      }
      return r.json() as Promise<{ acertou: boolean; limite?: typeof limiteQuery }>;
    },
    onSuccess: (data) => {
      setRespostaState((prev) => ({ ...prev, acertou: data.acertou }));
      if (data.limite) setLimiteLocal(data.limite as typeof limiteLocal);
      // Invalidações: estatísticas + limite + gabarito
      void queryClient.invalidateQueries({ queryKey: qk.cadernoSub(id, "estatisticas") });
      void queryClient.invalidateQueries({ queryKey: qk.cadernoSub(id, "stats-detalhe") });
      void queryClient.invalidateQueries({ queryKey: qk.cadernoSub(id, "gabarito") });
      void queryClient.invalidateQueries({ queryKey: qk.cadernoSub(id, "minhas-resolucoes") });
      void queryClient.invalidateQueries({ queryKey: qk.limite() });
    },
    onError: (err: unknown) => {
      const e = err as { isPaywall?: boolean; detail?: { detail?: { mensagem?: string } } };
      if (e.isPaywall) {
        setRespostaState((prev) => ({ ...prev, resolvida: false }));
        const msg = (e.detail as { detail?: { mensagem?: string } } | null)?.detail?.mensagem;
        setPaywall(msg || "Você atingiu o limite de questões de hoje do plano grátis.");
      } else {
        console.error(err);
        setRespostaState((prev) => ({ ...prev, resolvida: false }));
      }
    },
  });

  async function resolverQuestao() {
    if (!selecionada || !questao || !caderno || resolvida) return;
    const tempo_segundos = Math.round((Date.now() - startedAt.current) / 1000);
    setRespostaQid(questao.id);
    setRespostaState((prev) => ({ ...prev, resolvida: true }));
    responderMutation.mutate({
      qid: questao.id,
      resposta: selecionada,
      tempo_segundos,
      caderno_id: caderno.id,
    });
  }

  // ─── Mutation: favoritar (com optimistic update) ───
  const favoritarMutation = useMutation({
    mutationFn: (qid: number) => apiPost<{ favorita: boolean }>(`/api/q/${qid}/favoritar`),
    onMutate: async (qid) => {
      await queryClient.cancelQueries({ queryKey: qk.favoritas() });
      const prev = queryClient.getQueryData<{ ids: number[] }>(qk.favoritas());
      queryClient.setQueryData<{ ids: number[] }>(qk.favoritas(), (old) => {
        const currentIds = old?.ids ?? [];
        const isAlreadyFav = currentIds.includes(qid);
        return {
          ids: isAlreadyFav
            ? currentIds.filter((id) => id !== qid)
            : [...currentIds, qid],
        };
      });
      return { prev };
    },
    onError: (_e, _qid, ctx) => {
      if (ctx?.prev !== undefined) {
        queryClient.setQueryData(qk.favoritas(), ctx.prev);
      }
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: qk.favoritas() });
    },
  });

  const toggleFavorita = useCallback(() => {
    if (!currentQid) return;
    favoritarMutation.mutate(currentQid);
  }, [currentQid, favoritarMutation]);

  const annotations = useQuestionAnnotations(caderno?.id ?? null, currentQid ?? null);

  async function mudarIndice(proximoIdx: number) {
    if (!caderno) return;
    await annotations.flush();
    const novo = Math.max(0, Math.min(caderno.total - 1, proximoIdx));
    startedAt.current = Date.now();
    setRespostaQid(null); // reseta estado de resposta para a nova questão
    setIdx(novo);
  }

  function avancar(delta: number) {
    void mudarIndice(idx + delta);
  }

  function aleatoria() {
    if (!caderno) return;
    // Sorteia entre as NÃO resolvidas; se todas já foram, cai pra qualquer uma.
    const naoResolvidas = caderno.question_ids
      .map((qid, i) => ({ qid, i }))
      .filter(({ qid }) => !resolvidasSet.has(qid));
    if (naoResolvidas.length === 0) {
      void mudarIndice(Math.floor(Math.random() * caderno.total));
      return;
    }
    const escolha = naoResolvidas[Math.floor(Math.random() * naoResolvidas.length)];
    void mudarIndice(escolha.i);
  }

  function proximaNaoResolvida() {
    if (!caderno) return;
    const n = caderno.total;
    for (let step = 1; step <= n; step++) {
      const cand = (idx + step) % n;
      if (!resolvidasSet.has(caderno.question_ids[cand])) {
        void mudarIndice(cand);
        return;
      }
    }
    void avancar(1); // todas resolvidas → só avança
  }

  useHotkeys({
    ArrowLeft: () => { if (!canvasActive) avancar(-1); },
    ArrowRight: () => { if (!canvasActive) avancar(1); },
    l: () => { if (!canvasActive) aleatoria(); },
    n: () => { if (!canvasActive) proximaNaoResolvida(); },
    p: () => { if (!canvasActive) setGotoOpen(true); },
    m: () => { if (!canvasActive) toggleFavorita(); },
    j: () => { if (!canvasActive) toggleFavorita(); },
    "+": () => { if (!canvasActive) setFontSize((s) => Math.min(28, s + 2)); },
    "=": () => { if (!canvasActive) setFontSize((s) => Math.min(28, s + 2)); },
    "-": () => { if (!canvasActive) setFontSize((s) => Math.max(12, s - 2)); },
    "0": () => { if (!canvasActive) setFontSize(16); },
    ".": () => { if (!canvasActive) setPausado((p) => !p); },
    "?": () => { if (!canvasActive) setShowAtalhos(true); },
    f: () => { if (!canvasActive) setForumAberto((v) => !v); },
    Escape: () => setCanvasActive(false),
  }, { enabled: !calculatorOpen });

  // ─── Skeleton somente no carregamento inicial do caderno ───
  if (cadernoLoading || !caderno) return <div className="p-8 text-fg-muted">Carregando caderno…</div>;
  // Questão: keepPreviousData garante que a anterior fica visível enquanto a nova carrega
  if (!questao) return <div className="p-8 text-fg-muted">Carregando questão {idx + 1} de {caderno.total}…</div>;

  const taxa = stats.resolvidas > 0 ? Math.round((stats.acertos / stats.resolvidas) * 100) : 0;

  // Em CERTO_ERRADO o gabarito é palavra ("ERRADO") e a alternativa tem letra (B).
  // Regra: usa a flag `correta` quando existe; senão cai pro gabarito (letra em MC).
  const temFlagCorreta = questao.alternativas.some((a) => a.correta === true);
  const ehCorreta = (alt: Alternativa) =>
    temFlagCorreta ? alt.correta === true : alt.letra === questao.gabarito;
  const altCorreta = questao.alternativas.find(ehCorreta);
  const gabaritoLabel = temFlagCorreta
    ? `${altCorreta?.letra ?? "?"} (${(altCorreta?.texto_md || "").replace(/<[^>]+>/g, "").trim() || questao.gabarito})`
    : questao.gabarito;

  function isStruck(target: StrikeTarget) {
    return annotations.strikes.targets.some((item) => {
      if (item.type !== target.type) return false;
      if (item.type === "alternative" && target.type === "alternative") return item.id === target.id;
      if (item.type === "statement-block" && target.type === "statement-block") return item.index === target.index;
      return false;
    });
  }

  return (
    <div
      className="min-h-screen bg-page text-fg"
      style={{ fontSize }}
    >
      {/* ─── Top breadcrumb + timer ─── */}
      <div className="border-b border-border/60 px-6 py-2 flex items-center gap-3 text-xs sticky top-0 bg-page z-20">
        <span className="text-fg-faint">Estudo</span>
        <span className="text-fg-faint">›</span>
        <button
          onClick={() => router.push("/q/cadernos")}
          className="text-fg-faint hover:text-primary hover:underline"
        >
          Minhas pastas
        </button>
        <span className="text-fg-faint">›</span>
        <button
          onClick={() => router.push(`/q/cadernos?pasta=${encodeURIComponent(caderno.pasta ?? "")}`)}
          className="text-fg-faint hover:text-primary hover:underline truncate max-w-[24rem]"
          title={caderno.pasta ?? "Sem classificação"}
        >
          {caderno.pasta ?? "Sem classificação"}
        </button>
        <span className="text-fg-faint">›</span>
        <span className="text-fg-muted truncate max-w-[24rem]">{caderno.nome}</span>
        <a
          href={`/q/caderno/${id}/cronograma`}
          className="text-xs border border-border/60 rounded px-2 py-1 text-primary hover:bg-primary/10"
          title="Cronograma de estudo"
        >
          📅 Cronograma
        </a>
        <button
          onClick={() => router.push("/q/filtrar")}
          className="ml-auto text-fg-muted hover:text-fg"
          title="Voltar"
        >
          ✕
        </button>
        <div className="flex items-center gap-2 text-primary font-mono">
          <span>↔</span>
          <button
            onClick={() => setPausado((p) => !p)}
            className="hover:underline"
            title="Pausar relógio (.)"
          >
            ⏱ {formatTempo(tempo)}{pausado && " ⏸"}
          </button>
        </div>
      </div>

      {/* ─── Tabs ─── */}
      <nav className="border-b border-border/60 px-6 flex items-center gap-1 text-sm sticky top-[36px] bg-page z-10">
        {([
          ["Questoes", "🔍 Questões"],
          ["Indice", "≡ Índice"],
          ["Estatisticas", "⊞ Estatísticas"],
          ["Gabarito", "✓ Gabarito"],
          ["Configuracoes", "⚙ Configurações"],
          ["Imprimir", "🖨 Imprimir"],
        ] as const).map(([key, label]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={`px-4 py-2.5 border-b-2 transition ${
              tab === key
                ? "border-primary text-primary"
                : "border-transparent text-fg-muted hover:text-fg"
            }`}
          >
            {label}
          </button>
        ))}
        <button className="ml-auto px-4 py-2.5 text-primary hover:underline text-xs">
          🔗 Compartilhar
        </button>
      </nav>

      {tab === "Estatisticas" && (
        <EstatisticasTab cadernoId={caderno.id} cadernoNome={caderno.nome} />
      )}
      {tab === "Indice" && (
        <IndiceTab
          cadernoId={caderno.id}
          onAbrir={(n) => {
            void (async () => {
              await mudarIndice(n - 1);
              setTab("Questoes");
            })();
          }}
          idxAtual={idx}
        />
      )}
      {tab === "Gabarito" && (
        <GabaritoTab cadernoId={caderno.id} />
      )}
      {tab === "Configuracoes" && (
        <ConfigTab
          fontSize={fontSize} setFontSize={setFontSize}
          pausado={pausado} setPausado={setPausado}
          tempo={tempo}
        />
      )}
      {tab === "Imprimir" && (
        <div className="max-w-4xl mx-auto px-6 py-8 text-sm text-fg-faint italic">
          Aba &quot;Imprimir&quot; — gera PDF do caderno (em breve via /api/q/cadernos/{caderno.id}/pdf).
        </div>
      )}

      {tab === "Questoes" && (
      <main className="max-w-5xl mx-auto px-6 py-4">
        {/* ─── Card stats da questão ─── */}
        <div ref={questionCardRef} className="relative mb-4 rounded-lg border border-border/60 bg-surface">
          <QuestionCanvasOverlay
            active={canvasActive}
            canvas={annotations.canvas}
            tool={canvasTool}
            color={canvasColor}
            width={canvasWidth}
            onChange={annotations.updateCanvas}
          />
          <header className="px-4 py-3 flex items-center gap-4 border-b border-border/60">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-cyan-600 to-violet-600 flex items-center justify-center text-xl shrink-0">
              {questao.banca?.sigla?.slice(0, 2).toUpperCase() || "?"}
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-semibold flex items-center gap-2 flex-wrap">
                Questão <span className="text-primary">{idx + 1}</span> de {caderno.total}
                <span className="text-xs font-normal">
                  (
                  <button
                    type="button"
                    disabled={stats.resolvidas === 0}
                    onClick={() => derivarCaderno("resolvidas")}
                    title="Gerar um caderno só com as questões resolvidas"
                    className="text-primary underline decoration-primary/60 underline-offset-2 hover:decoration-primary disabled:no-underline disabled:cursor-default"
                  >
                    {stats.resolvidas} Resolvidas
                  </button>
                  ,{" "}
                  <button
                    type="button"
                    disabled={stats.acertos === 0}
                    onClick={() => derivarCaderno("acertadas")}
                    title="Gerar um caderno só com as questões que você acertou"
                    className="text-success underline decoration-success/60 underline-offset-2 hover:decoration-success disabled:no-underline disabled:cursor-default"
                  >
                    {stats.acertos} Acertos
                  </button>{" "}
                  e{" "}
                  <button
                    type="button"
                    disabled={stats.erros === 0}
                    onClick={() => derivarCaderno("erradas")}
                    title="Gerar um caderno só com as questões que você errou"
                    className="text-error underline decoration-error/60 underline-offset-2 hover:decoration-error disabled:no-underline disabled:cursor-default"
                  >
                    {stats.erros} Erros
                  </button>
                  {stats.resolvidas > 0 && `, ${taxa}% acerto`}) ✕
                </span>
                {fav && <span className="text-yellow-400">⭐</span>}
              </div>
              <div className="text-xs text-fg-muted mt-0.5">
                <span className="text-fg-faint">Matéria:</span>{" "}
                <a href={`/q/filtrar?materia=${encodeURIComponent(questao.materia?.nome || "")}`} className="text-primary hover:underline">
                  {questao.materia?.nome}
                </a>
                <br />
                <span className="text-fg-faint">Assunto:</span>{" "}
                {questao.assuntos.map((a, i) => (
                  <span key={a.id}>
                    {i > 0 && ", "}
                    <a href={`/q/filtrar?assunto=${encodeURIComponent(a.nome)}`} className="text-primary hover:underline">
                      {a.nome}
                    </a>
                  </span>
                ))}
                {questao.assuntos.length === 0 && <span className="text-fg-faint">Sem classificação</span>}
              </div>
            </div>
            {/* flex-1 (basis 0) impede a toolbar de reivindicar a largura
                max-content e esmagar o título; ela quebra no próprio espaço. */}
            <div className="flex flex-1 min-w-0 flex-wrap items-center justify-end gap-2 text-lg text-fg-faint">
              <CanvasToolbar
                active={canvasActive}
                tool={canvasTool}
                color={canvasColor}
                width={canvasWidth}
                hasStrokes={annotations.canvas.strokes.length > 0}
                saving={annotations.saving}
                saveError={annotations.saveError}
                onActiveChange={setCanvasActive}
                onToolChange={setCanvasTool}
                onColorChange={setCanvasColor}
                onWidthChange={setCanvasWidth}
                onClear={annotations.clearCanvas}
                onOpenCalculator={() => setCalculatorOpen(true)}
              />
              <button title="Comentário (O)" className="hover:text-primary">🎓</button>
              <button title="Teoria" className="hover:text-primary">📕</button>
              <button
                title="Fórum (F)"
                onClick={() => setForumAberto((v) => !v)}
                className={`relative ${forumAberto ? "text-primary" : "hover:text-primary"}`}
              >
                💬
                {(questao.forum_count ?? 0) > 0 && (
                  <span className="absolute -right-1 -top-1 rounded-full bg-primary px-1 text-[10px] font-bold leading-tight text-black">
                    {questao.forum_count}
                  </span>
                )}
              </button>
              <button title="Favoritar (M)" onClick={toggleFavorita} className={fav ? "text-yellow-400" : "hover:text-yellow-400"}>
                {fav ? "★" : "☆"}
              </button>
              <button title="Anotação (W)" className="hover:text-primary">✏️</button>
              <button title="Estatísticas" className="hover:text-primary">⭕</button>
              <button title="Mais opções" className="hover:text-primary">⋮</button>
            </div>
          </header>

          {forumAberto && currentQid != null && (
            <ForumPanel questaoId={currentQid} onFechar={() => setForumAberto(false)} />
          )}

          {/* ─── Linha enxuta com código + banca ─── */}
          <div className="px-4 py-2 bg-surface-2 border-b border-border/60 text-xs flex items-center gap-2">
            <span className="text-fg-faint">🔗</span>
            <span className="text-primary font-mono">#{questao.id_externo}</span>
            <span className="font-semibold text-fg">{questao.banca?.sigla}</span>
            <span className="text-fg-faint">-</span>
            <span className="text-fg-muted">
              {questao.cargo?.ano} - {questao.cargo?.nome} / {questao.orgao?.sigla} / {questao.cargo?.ano}
            </span>
            {questao.status === "ANULADA" && (
              <span className="ml-2 px-2 py-0.5 bg-warning/15 text-warning rounded text-[10px] font-semibold border border-warning/40">ANULADA</span>
            )}
            <button className="ml-auto text-fg-faint hover:text-fg" title="Reportar erro">↗</button>
            <button className="text-fg-faint hover:text-fg" title="Anterior (←)" onClick={() => avancar(-1)}>←</button>
            <button className="text-fg-faint hover:text-fg" title="Próxima (→)" onClick={() => avancar(1)}>→</button>
          </div>

          {/* ─── Enunciado + alternativas ─── */}
          {/* key={questao.id}: a transição dispara quando a NOVA questão chega
              (cache hit = instantâneo + fade; cache miss = mantém a anterior e
              faz fade ao trocar), mascarando o swap sem parecer lag. */}
          <div key={questao.id} className="p-5 q-swap">
            <QuestionHtml
              as="article"
              onDoubleClick={() => annotations.toggleStrike({ type: "statement-block", index: 0 })}
              className={`prose prose-invert prose-cyan max-w-none mb-4 ${
                isStruck({ type: "statement-block", index: 0 }) ? "text-gray-500 line-through decoration-red-500 decoration-2" : ""
              }`}
              title="Dois cliques riscam ou restauram o enunciado"
              html={questao.enunciado_html}
            />

            <ol className="space-y-1.5 mb-5">
              {questao.alternativas.map((alt) => {
                const isCorreta = resolvida && ehCorreta(alt);
                const isErrada = resolvida && selecionada === alt.letra && !ehCorreta(alt);
                return (
                  <li key={alt.id}>
                    <StrikableAlternative
                      id={alt.id}
                      letra={alt.letra}
                      selected={selecionada === alt.letra}
                      disabled={resolvida}
                      struck={isStruck({ type: "alternative", id: alt.id })}
                      onSelect={() => {
                        // Estado FRESCO p/ a questão atual: não espalhar `prev`, que
                        // ainda carrega resolvida/acertou da questão anterior (bug:
                        // ao clicar numa alternativa da próxima questão ela já
                        // aparecia "resolvida/errada"). Seleção só ocorre pré-resolução
                        // (alternativa fica disabled quando resolvida).
                        setRespostaQid(currentQid ?? null);
                        setRespostaState({ selecionada: alt.letra, resolvida: false, acertou: null });
                      }}
                      onToggleStrike={() => annotations.toggleStrike({ type: "alternative", id: alt.id })}
                      className={`w-full text-left flex items-start gap-3 px-3 py-2 rounded border transition ${
                        isCorreta ? "border-success bg-success/10" :
                        isErrada ? "border-error bg-error/10" :
                        selecionada === alt.letra ? "border-primary bg-primary/10" :
                        "border-border hover:bg-surface-2/40"
                      }`}
                    >
                      <QuestionHtml as="span" className="flex-1" html={alt.texto_html || alt.texto_md || ""} />
                    </StrikableAlternative>
                  </li>
                );
              })}
            </ol>

            {!resolvida && (
              <button
                onClick={resolverQuestao}
                disabled={!selecionada}
                className="bg-green-600 hover:bg-green-500 disabled:bg-surface-2 disabled:cursor-not-allowed px-6 py-2 rounded font-semibold uppercase tracking-wide text-sm"
              >
                Resolver Questão
              </button>
            )}

            {resolvida && acertou !== null && (
              <div className={`p-3 rounded text-sm font-medium ${
                acertou ? "bg-success/15 border border-success/40 text-success" :
                "bg-error/15 border border-error/40 text-error"
              }`}>
                {acertou ? "✓ Você acertou!" : `✗ Resposta esperada: ${gabaritoLabel}`}
              </div>
            )}

            {/* ─── Bottom nav (estilo TC) ─── */}
            <nav className="mt-6 pt-4 border-t border-border/60 flex items-center gap-1 flex-wrap">
              <NavBtn icon="←" title="Anterior (←)" onClick={() => avancar(-1)} disabled={idx === 0} />
              <NavBtn icon="→" title="Próxima (→)" onClick={() => avancar(1)} disabled={idx === caderno.total - 1} />
              <NavBtn icon="🔀" title="Aleatória não resolvida (L)" onClick={aleatoria} />
              <NavBtn icon="→⊟" title="Próxima não resolvida (N)" onClick={proximaNaoResolvida} />
              <NavBtn icon="◀" title="Tópico anterior (Z)" onClick={() => avancar(-1)} />
              <NavBtn icon="▶" title="Tópico seguinte (X)" onClick={() => avancar(1)} />
              <NavBtn icon="↺" title="Desfazer (Ctrl+Z)" onClick={() => avancar(-1)} />
              <NavBtn icon="★" title="Próxima favorita (V)" onClick={() => avancar(1)} />
              <NavBtn icon="✎" title="Próxima anotada (U)" onClick={() => avancar(1)} />

              <span className="ml-auto text-xs text-fg-faint">{idx + 1} / {caderno.total}</span>
            </nav>

            <div className="mt-3 text-xs text-fg-faint flex items-center gap-1">
              <span className="text-red-500">⊘</span>
              <span>Encontrou algum erro nesta questão?</span>
              <button className="text-primary hover:underline">Fale conosco</button>
              <button onClick={() => setShowAtalhos(true)} className="ml-auto text-primary hover:underline">
                ⓘ Lista das teclas de atalho
              </button>
            </div>
          </div>
        </div>
      </main>
      )}

      <ScientificCalculator
        open={calculatorOpen}
        cadernoId={caderno.id}
        questaoId={questao.id}
        onClose={() => setCalculatorOpen(false)}
      />

      {/* ─── Modal atalhos ─── */}
      {showAtalhos && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50" onClick={() => setShowAtalhos(false)}>
          <div className="bg-surface border border-border rounded-lg p-6 max-w-2xl w-full max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-4">Atalhos de teclado</h2>
            {(["nav", "acao", "ui"] as const).map((grupo) => (
              <div key={grupo} className="mb-4">
                <h3 className="text-xs uppercase tracking-wider text-primary mb-2">
                  {grupo === "nav" ? "Navegação" : grupo === "acao" ? "Ações" : "Interface"}
                </h3>
                <table className="w-full text-sm">
                  <tbody>
                    {Object.entries(ATALHOS_TC)
                      .filter(([, v]) => v.group === grupo)
                      .map(([k, v]) => (
                        <tr key={k}>
                          <td className="py-1 pr-4 font-mono text-primary">{k}</td>
                          <td className="py-1 text-fg">{v.label}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            ))}
            <button onClick={() => setShowAtalhos(false)} className="mt-4 text-xs text-fg-muted hover:text-fg">
              Fechar (Esc)
            </button>
          </div>
        </div>
      )}

      {/* ─── Modal ir para questão (P) ─── */}
      {gotoOpen && caderno && (
        <div
          className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center z-50"
          onClick={() => { setGotoOpen(false); setGotoValue(""); }}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const n = parseInt(gotoValue, 10);
              if (!Number.isNaN(n)) void mudarIndice(Math.min(Math.max(n, 1), caderno.total) - 1);
              setGotoOpen(false);
              setGotoValue("");
            }}
            onClick={(e) => e.stopPropagation()}
            className="bg-surface-dark border border-border rounded-lg p-6 w-full max-w-sm shadow-xl"
          >
            <h2 className="text-lg font-semibold mb-1">Ir para questão</h2>
            <p className="text-sm text-fg-muted mb-4">Digite um número entre 1 e {caderno.total}.</p>
            <input
              autoFocus
              type="number"
              min={1}
              max={caderno.total}
              value={gotoValue}
              onChange={(e) => setGotoValue(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Escape") { setGotoOpen(false); setGotoValue(""); } }}
              placeholder={`1 – ${caderno.total}`}
              className="w-full bg-bg-dark border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary mb-5"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => { setGotoOpen(false); setGotoValue(""); }}
                className="px-4 py-2 text-sm rounded-md border border-border text-fg hover:bg-surface-2 transition"
              >
                Cancelar
              </button>
              <button type="submit" className="px-4 py-2 text-sm rounded-md bg-cyan-600 hover:bg-cyan-500 font-medium transition">
                Ir
              </button>
            </div>
          </form>
        </div>
      )}

      {/* ─── Contador do limite diário (plano grátis) ─── */}
      {limite && !limite.ilimitado && (
        <button
          onClick={() => router.push("/assinar")}
          title="Limite diário do plano grátis — clique para assinar"
          className="fixed bottom-4 right-4 z-40 flex items-center gap-1.5 rounded-full border border-border-dark bg-surface-dark/95 px-3 py-1.5 text-xs font-medium text-fg shadow-lg backdrop-blur hover:border-secondary/50 hover:text-white transition"
        >
          <span className="material-symbols-outlined text-[16px] text-secondary">bolt</span>
          {limite.usado}/{limite.limite} hoje
        </button>
      )}

      {/* ─── Paywall: limite diário atingido ─── */}
      {paywall && (
        <div className="fixed inset-0 z-60 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4" onClick={() => setPaywall(null)}>
          <div className="w-full max-w-sm rounded-2xl border border-secondary/30 bg-surface-dark p-7 text-center shadow-xl" onClick={(e) => e.stopPropagation()}>
            <span className="material-symbols-outlined text-secondary text-5xl">workspace_premium</span>
            <h2 className="mt-3 text-lg font-bold text-fg-strong">Limite diário atingido</h2>
            <p className="mt-2 text-sm text-fg-muted">{paywall}</p>
            <button
              onClick={() => router.push("/assinar")}
              className="mt-6 w-full rounded-lg bg-secondary py-2.5 text-sm font-semibold text-white hover:opacity-90 transition"
            >
              Assinar studIA Pro
            </button>
            <button onClick={() => setPaywall(null)} className="mt-2 w-full rounded-lg py-2 text-xs text-fg-faint hover:text-fg">
              Continuar amanhã
            </button>
          </div>
        </div>
      )}

      {/* ─── Derivar caderno pelo cabeçalho (Resolvidas/Acertos/Erros) ─── */}
      {derivarModais}
    </div>
  );
}

function NavBtn({
  icon,
  title,
  onClick,
  disabled,
}: {
  icon: string;
  title: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      title={title}
      className="w-10 h-10 border border-border hover:bg-surface-2 disabled:opacity-30 rounded flex items-center justify-center text-base"
    >
      {icon}
    </button>
  );
}

// ════════════════════════════ ESTATÍSTICAS ════════════════════════════

interface StatsDetalhe {
  resolvidas: number;
  acertos: number;
  erros: number;
  taxa: number;
  questoes_total: number;
  tempo_total_segundos: number;
  tempo_medio_segundos: number;
  por_materia: Array<{ nome: string; resolvidas: number; acertos: number; taxa: number }>;
  por_assunto: Array<{ nome: string; resolvidas: number; acertos: number; taxa: number }>;
  por_banca: Array<{ nome: string; resolvidas: number; acertos: number; taxa: number }>;
  ultimas_resolucoes: Array<{
    id_externo: number; resposta: string; acertou: boolean;
    tempo_segundos: number; created_at: string;
  }>;
}

type TipoDerivar = "resolvidas" | "acertadas" | "erradas";
const LABEL_DERIVAR: Record<TipoDerivar, string> = {
  resolvidas: "Resolvidas",
  acertadas: "Acertadas",
  erradas: "Erradas",
};

// Lógica compartilhada de "derivar caderno" (cards da aba Estatísticas e
// cabeçalho da questão). Retorna o disparador e a UI dos modais para embutir.
function useDerivarCaderno(cadernoId: number, cadernoNome: string) {
  const router = useRouter();
  const [dialog, setDialog] = useState<{ tipo: TipoDerivar; nome: string } | null>(null);
  const [erro, setErro] = useState<string | null>(null);
  const [criado, setCriado] = useState<{ id: number; nome: string; total: number } | null>(null);

  const derivarMutation = useMutation({
    mutationFn: (body: { tipo: TipoDerivar; nome: string }) =>
      apiPost<{ id: number; nome: string; total: number }>(`/api/q/cadernos/${cadernoId}/derivar`, body),
    onSuccess: (res) => {
      setCriado(res);
      setDialog(null);
      setErro(null);
    },
    onError: (e: unknown) => {
      const msg = e instanceof Error ? e.message : "Não foi possível criar o caderno.";
      setErro(msg);
    },
  });

  function abrirDialog(tipo: TipoDerivar) {
    setErro(null);
    setDialog({ tipo, nome: `${LABEL_DERIVAR[tipo]} — ${cadernoNome}` });
  }

  const modais = (
    <>
      {/* ─── Dialog próprio: criar caderno derivado ─── */}
      {dialog && (
        <div
          className="fixed inset-0 z-60 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          role="dialog"
          aria-modal="true"
          onClick={() => !derivarMutation.isPending && setDialog(null)}
        >
          <div className="w-full max-w-md rounded-2xl border border-primary/30 bg-surface-dark p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-bold text-fg-strong">
              Criar caderno com as <span className="text-primary">{LABEL_DERIVAR[dialog.tipo].toLowerCase()}</span>
            </h2>
            <p className="mt-1 text-sm text-fg-muted">
              Um caderno novo será criado com {dialog.tipo === "acertadas" ? "as questões que você acertou" : dialog.tipo === "erradas" ? "as questões que você errou" : "todas as questões que você resolveu"} neste caderno.
            </p>
            <label className="mt-4 block text-xs text-fg-faint">Nome do caderno</label>
            <input
              autoFocus
              value={dialog.nome}
              onChange={(e) => setDialog((d) => (d ? { ...d, nome: e.target.value } : d))}
              onKeyDown={(e) => { if (e.key === "Enter" && dialog.nome.trim()) derivarMutation.mutate(dialog); }}
              className="mt-1 w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-primary"
            />
            {erro && <p className="mt-2 text-xs text-error">{erro}</p>}
            <div className="mt-5 flex gap-2">
              <button
                onClick={() => derivarMutation.mutate(dialog)}
                disabled={!dialog.nome.trim() || derivarMutation.isPending}
                className="flex-1 rounded-lg bg-primary py-2.5 text-sm font-semibold text-black hover:opacity-90 disabled:opacity-40 transition"
              >
                {derivarMutation.isPending ? "Criando…" : "Criar caderno"}
              </button>
              <button
                onClick={() => setDialog(null)}
                disabled={derivarMutation.isPending}
                className="rounded-lg border border-border px-4 py-2.5 text-sm text-fg-muted hover:text-fg disabled:opacity-40"
              >
                Cancelar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ─── Aviso de caderno criado (fica na tela, com link) ─── */}
      {criado && (
        <div
          className="fixed inset-0 z-60 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
          role="dialog"
          aria-modal="true"
          onClick={() => setCriado(null)}
        >
          <div className="w-full max-w-sm rounded-2xl border border-success/30 bg-surface-dark p-7 text-center shadow-xl" onClick={(e) => e.stopPropagation()}>
            <span className="material-symbols-outlined text-success text-5xl">task_alt</span>
            <h2 className="mt-3 text-lg font-bold text-fg-strong">Caderno criado</h2>
            <p className="mt-2 text-sm text-fg-muted">
              <span className="text-fg">{criado.nome}</span> — {criado.total} {criado.total === 1 ? "questão" : "questões"}.
            </p>
            <button
              onClick={() => router.push(`/q/caderno/${criado.id}`)}
              className="mt-6 w-full rounded-lg bg-primary py-2.5 text-sm font-semibold text-black hover:opacity-90 transition"
            >
              Abrir caderno
            </button>
            <button onClick={() => setCriado(null)} className="mt-2 w-full rounded-lg py-2 text-xs text-fg-faint hover:text-fg">
              Continuar aqui
            </button>
          </div>
        </div>
      )}
    </>
  );

  return { abrirDialog, modais };
}

function EstatisticasTab({ cadernoId, cadernoNome }: { cadernoId: number; cadernoNome: string }) {
  const { data, isPending } = useQuery<StatsDetalhe>({
    queryKey: qk.cadernoSub(cadernoId, "stats-detalhe"),
    queryFn: () => apiJson(`/api/q/cadernos/${cadernoId}/stats-detalhe`),
    staleTime: 30_000,
  });

  // Clicar num card abre confirmação com nome editável; ao confirmar, cria um
  // caderno derivado e avisa (lógica compartilhada via useDerivarCaderno).
  const { abrirDialog, modais } = useDerivarCaderno(cadernoId, cadernoNome);

  if (isPending || !data) return <div className="p-8 text-fg-muted">Carregando estatísticas…</div>;

  const progresso = data.questoes_total > 0 ? Math.round((data.resolvidas / data.questoes_total) * 100) : 0;

  return (
    <main className="max-w-5xl mx-auto px-6 py-6 space-y-6">
      {/* ─── Resumo grande ─── */}
      <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Card label="Resolvidas" value={data.resolvidas} sub={`de ${data.questoes_total}`} color="cyan"
          onClick={data.resolvidas > 0 ? () => abrirDialog("resolvidas") : undefined} />
        <Card label="Acertos" value={data.acertos} sub={`${data.taxa}% taxa`} color="green"
          onClick={data.acertos > 0 ? () => abrirDialog("acertadas") : undefined} />
        <Card label="Erros" value={data.erros} color="red"
          onClick={data.erros > 0 ? () => abrirDialog("erradas") : undefined} />
        <Card label="Tempo total" value={formatTempo(data.tempo_total_segundos)} mono color="violet" />
        <Card label="Médio/questão" value={data.tempo_medio_segundos > 0 ? `${Math.round(data.tempo_medio_segundos)}s` : "—"} color="amber" />
      </section>

      {/* ─── Barra de progresso do caderno ─── */}
      <section className="border border-border/60 rounded-lg bg-surface p-4">
        <div className="flex items-center justify-between mb-2 text-sm">
          <span className="text-fg-muted">Progresso no caderno</span>
          <span className="text-primary font-semibold">{progresso}%</span>
        </div>
        <div className="h-3 bg-surface-2 rounded overflow-hidden">
          <div
            className="h-full bg-gradient-to-r from-cyan-500 to-violet-500 transition-all"
            style={{ width: `${progresso}%` }}
          />
        </div>
      </section>

      {/* ─── Por matéria ─── */}
      {data.por_materia.length > 0 && (
        <BarBlock titulo="Desempenho por Matéria" items={data.por_materia} />
      )}

      {/* ─── Por assunto ─── */}
      {data.por_assunto.length > 0 && (
        <BarBlock titulo="Desempenho por Assunto (top 30)" items={data.por_assunto} />
      )}

      {/* ─── Por banca ─── */}
      {data.por_banca.length > 1 && (
        <BarBlock titulo="Desempenho por Banca" items={data.por_banca} />
      )}

      {/* ─── Últimas resoluções ─── */}
      {data.ultimas_resolucoes.length > 0 && (
        <section className="border border-border/60 rounded-lg bg-surface p-4">
          <h3 className="text-sm font-semibold mb-3 text-fg">Últimas 20 resoluções</h3>
          <table className="w-full text-xs">
            <thead className="text-fg-faint border-b border-border/60">
              <tr>
                <th className="text-left py-1.5 px-2">Questão</th>
                <th className="text-left py-1.5 px-2">Resposta</th>
                <th className="text-left py-1.5 px-2">Resultado</th>
                <th className="text-right py-1.5 px-2">Tempo</th>
                <th className="text-right py-1.5 px-2">Quando</th>
              </tr>
            </thead>
            <tbody>
              {data.ultimas_resolucoes.map((r, i) => (
                <tr key={i} className="border-b border-border/60">
                  <td className="py-1.5 px-2 font-mono text-primary">Q{r.id_externo}</td>
                  <td className="py-1.5 px-2 font-mono">{r.resposta}</td>
                  <td className={`py-1.5 px-2 ${r.acertou ? "text-success" : "text-error"}`}>
                    {r.acertou ? "✓ Acerto" : "✗ Erro"}
                  </td>
                  <td className="py-1.5 px-2 text-right text-fg-muted">
                    {r.tempo_segundos ? `${r.tempo_segundos}s` : "—"}
                  </td>
                  <td className="py-1.5 px-2 text-right text-fg-faint">
                    {new Date(r.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {data.resolvidas === 0 && (
        <div className="text-center py-12 text-fg-faint text-sm">
          Resolva algumas questões para ver suas estatísticas aqui.
        </div>
      )}

      {modais}
    </main>
  );
}

function Card({ label, value, sub, color, mono, onClick }: {
  label: string; value: string | number; sub?: string;
  color: "cyan" | "green" | "red" | "violet" | "amber";
  mono?: boolean;
  onClick?: () => void;
}) {
  const colors = {
    cyan: "text-primary",
    green: "text-success",
    red: "text-error",
    violet: "text-secondary",
    amber: "text-warning",
  };
  const inner = (
    <>
      <div className={`text-2xl font-bold ${colors[color]} ${mono ? "font-mono" : ""}`}>{value}</div>
      <div className="text-xs text-fg-muted mt-1">{label}</div>
      {sub && <div className="text-xs text-fg-faint">{sub}</div>}
    </>
  );
  if (onClick) {
    return (
      <button
        onClick={onClick}
        title="Criar um caderno só com essas questões"
        className="border border-border/60 rounded-lg bg-surface p-4 text-left transition hover:border-primary/50 hover:bg-surface-2/40 focus:outline-none focus:ring-1 focus:ring-primary/50"
      >
        {inner}
        <div className="text-[10px] text-primary/70 mt-1.5">+ gerar caderno →</div>
      </button>
    );
  }
  return <div className="border border-border/60 rounded-lg bg-surface p-4">{inner}</div>;
}

function BarBlock({ titulo, items }: {
  titulo: string;
  items: Array<{ nome: string; resolvidas: number; acertos: number; taxa: number }>;
}) {
  const max = Math.max(...items.map((i) => i.resolvidas), 1);
  return (
    <section className="border border-border/60 rounded-lg bg-surface p-4">
      <h3 className="text-sm font-semibold mb-3 text-fg">{titulo}</h3>
      <div className="space-y-2">
        {items.map((it) => (
          <div key={it.nome} className="text-xs">
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-fg truncate flex-1 mr-2">{it.nome}</span>
              <span className="text-fg-faint whitespace-nowrap">
                {it.acertos}/{it.resolvidas}
                <span className={`ml-2 font-semibold ${it.taxa >= 70 ? "text-success" : it.taxa >= 50 ? "text-warning" : "text-error"}`}>
                  {it.taxa}%
                </span>
              </span>
            </div>
            <div className="h-1.5 bg-surface-2 rounded overflow-hidden flex">
              <div className="h-full bg-green-500" style={{ width: `${(it.acertos / max) * 100}%` }} />
              <div className="h-full bg-red-500" style={{ width: `${((it.resolvidas - it.acertos) / max) * 100}%` }} />
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

// ════════════════════════════ ÍNDICE ════════════════════════════

interface IndiceItem {
  n: number;
  questao_id: number;
  id_externo: number;
  banca: string | null;
  materia: string | null;
  gabarito: string | null;
  tipo: string | null;
  preview: string;
}

function IndiceTab({ cadernoId, onAbrir, idxAtual }: {
  cadernoId: number; onAbrir: (n: number) => void; idxAtual: number;
}) {
  const [filtro, setFiltro] = useState("");

  const { data } = useQuery<{ items: IndiceItem[] }>({
    queryKey: qk.cadernoSub(cadernoId, "indice"),
    queryFn: () => apiJson(`/api/q/cadernos/${cadernoId}/indice`),
    staleTime: 5 * 60 * 1000,
  });
  const items = data?.items ?? [];

  const filtrados = filtro
    ? items.filter((i) =>
        (i.materia || "").toLowerCase().includes(filtro.toLowerCase()) ||
        (i.banca || "").toLowerCase().includes(filtro.toLowerCase()) ||
        i.preview.toLowerCase().includes(filtro.toLowerCase()) ||
        String(i.id_externo).includes(filtro)
      )
    : items;

  return (
    <main className="max-w-5xl mx-auto px-6 py-6">
      <div className="flex items-center gap-3 mb-4">
        <input
          type="text"
          value={filtro}
          onChange={(e) => setFiltro(e.target.value)}
          placeholder="Filtrar por matéria, banca, ID ou texto…"
          className="flex-1 px-3 py-2 bg-surface-2 border border-border rounded text-sm focus:outline-none focus:border-primary"
        />
        <span className="text-xs text-fg-faint">{filtrados.length} / {items.length}</span>
      </div>

      <div className="border border-border/60 rounded-lg overflow-hidden">
        <div className="max-h-[70vh] overflow-y-auto">
          {filtrados.map((it) => (
            <button
              key={it.questao_id}
              onClick={() => onAbrir(it.n)}
              className={`w-full text-left px-4 py-2.5 border-b border-border/60 hover:bg-surface-2/40 flex items-start gap-3 ${
                it.n === idxAtual + 1 ? "bg-primary/10 border-l-2 border-l-primary" : ""
              }`}
            >
              <span className="font-mono text-xs text-fg-faint w-12 shrink-0 pt-0.5">#{it.n}</span>
              <div className="flex-1 min-w-0">
                <div className="text-xs text-fg-muted flex gap-2 mb-0.5">
                  <span className="text-primary font-mono">Q{it.id_externo}</span>
                  <span className="text-fg-faint">·</span>
                  <span>{it.banca}</span>
                  <span className="text-fg-faint">·</span>
                  <span className="truncate">{it.materia}</span>
                </div>
                <div className="text-xs text-fg-faint truncate">{it.preview}…</div>
              </div>
              <span className="font-mono text-xs text-fg-faint shrink-0 pt-0.5">
                {it.gabarito && (
                  <span className="bg-surface-2 px-1.5 py-0.5 rounded">
                    {it.gabarito.length > 4 ? "—" : it.gabarito}
                  </span>
                )}
              </span>
            </button>
          ))}
        </div>
      </div>
    </main>
  );
}

// ════════════════════════════ GABARITO ════════════════════════════

interface GabaritoItem {
  n: number;
  id_externo: number;
  gabarito: string | null;
  status: string | null;
}

function GabaritoTab({ cadernoId }: { cadernoId: number }) {
  const { data } = useQuery<{ items: GabaritoItem[] }>({
    queryKey: qk.cadernoSub(cadernoId, "gabarito"),
    queryFn: () => apiJson(`/api/q/cadernos/${cadernoId}/gabarito`),
    staleTime: 30_000,
  });
  const items = data?.items ?? [];

  function corDe(g: string | null) {
    if (!g) return "text-fg-faint";
    if (g.includes("ANULADA")) return "text-warning bg-warning/10 border-warning/40";
    if (g === "CERTO") return "text-success bg-success/10 border-success/40";
    if (g === "ERRADO") return "text-error bg-error/10 border-error/40";
    return "text-primary bg-primary/10 border-primary/40";
  }

  function abrev(g: string | null) {
    if (!g) return "—";
    if (g === "CERTO") return "C";
    if (g === "ERRADO") return "E";
    if (g.includes("ANULADA")) return "X";
    return g;
  }

  return (
    <main className="max-w-5xl mx-auto px-6 py-6">
      <h3 className="text-sm font-semibold mb-3 text-fg">
        Gabarito do caderno ({items.length} questões)
      </h3>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(64px,1fr))] gap-1.5">
        {items.map((it) => (
          <div
            key={it.n}
            className={`border border-border/60 rounded p-1.5 text-center text-xs ${corDe(it.gabarito)}`}
            title={`Q${it.id_externo} — ${it.gabarito || "?"}`}
          >
            <div className="text-[10px] text-fg-faint font-mono mb-0.5">{it.n})</div>
            <div className="font-bold font-mono">{abrev(it.gabarito)}</div>
          </div>
        ))}
      </div>
    </main>
  );
}

// ════════════════════════════ CONFIGURAÇÕES ════════════════════════════

function ConfigTab({
  fontSize, setFontSize, pausado, setPausado, tempo,
}: {
  fontSize: number; setFontSize: (n: number) => void;
  pausado: boolean; setPausado: (b: boolean) => void;
  tempo: number;
}) {
  return (
    <main className="max-w-3xl mx-auto px-6 py-6 space-y-5">
      <div className="border border-border/60 rounded-lg bg-surface p-4">
        <h3 className="text-sm font-semibold text-fg mb-3">Cronômetro</h3>
        <div className="flex items-center gap-3">
          <div className="text-2xl font-mono text-primary">{formatTempo(tempo)}</div>
          <button
            onClick={() => setPausado(!pausado)}
            className="bg-surface-2 hover:bg-surface-2/80 px-4 py-2 rounded text-sm"
          >
            {pausado ? "▶ Retomar" : "⏸ Pausar"} <span className="text-xs text-fg-faint">(.)</span>
          </button>
        </div>
      </div>

      <div className="border border-border/60 rounded-lg bg-surface p-4">
        <h3 className="text-sm font-semibold text-fg mb-3">Tamanho da fonte</h3>
        <div className="flex items-center gap-3">
          <button onClick={() => setFontSize(Math.max(12, fontSize - 2))} className="w-10 h-10 border border-border rounded hover:bg-surface-2">−</button>
          <div className="font-mono text-primary w-14 text-center">{fontSize}px</div>
          <button onClick={() => setFontSize(Math.min(28, fontSize + 2))} className="w-10 h-10 border border-border rounded hover:bg-surface-2">+</button>
          <button onClick={() => setFontSize(16)} className="ml-3 text-xs text-fg-muted hover:text-fg underline">Padrão (0)</button>
        </div>
      </div>

      <div className="border border-border/60 rounded-lg bg-surface p-4 text-xs text-fg-muted space-y-1">
        <div><strong className="text-fg">Modo de resolução:</strong> Sequencial (próximo idx)</div>
        <div><strong className="text-fg">Ordem das questões:</strong> Aleatória fixa (definida na criação)</div>
        <div><strong className="text-fg">Mostrar gabarito após responder:</strong> Sim</div>
      </div>
    </main>
  );
}

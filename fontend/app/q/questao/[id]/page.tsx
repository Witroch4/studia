"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { useHotkeys, ATALHOS_TC } from "../../../hooks/useHotkeys";
import QuestionHtml from "../../../components/QuestionHtml";
import { Skeleton } from "../../../components/ds/Skeleton";
import { ForumPanel } from "../../caderno/[id]/components/ForumPanel";
import { ApiError, apiJson, apiPost } from "@/lib/api";
import { useSession } from "@/lib/auth-client";
import { celebrarMetaDiaria } from "@/lib/confetti";
import { qk } from "@/lib/queryKeys";

interface Alternativa {
  id: number;
  letra: string;
  texto_md: string;
  texto_html: string | null;
  correta: boolean | null;
  ordem: number;
}

interface CadernoResumo {
  id: number;
  nome: string;
  pasta: string | null;
  total?: number;
}

interface Questao {
  id: number;
  id_externo: number;
  enunciado_md: string;
  enunciado_html: string;
  tipo: string;
  gabarito: string;
  status: string;
  banca: { sigla: string; nome: string } | null;
  orgao: { sigla: string; nome: string } | null;
  cargo: { nome: string; ano: number } | null;
  materia: { id?: number; nome: string } | null;
  assuntos: { id?: number; nome: string }[];
  alternativas: Alternativa[];
  forum_count?: number;
  forum_count_professores?: number;
  favorita: boolean;
  minha_resolucao: { resposta: string | null; acertou: boolean | null } | null;
  cadernos: CadernoResumo[];
}

interface ResponderResp {
  acertou: boolean | null;
  gabarito: string;
  ja_resolvida?: boolean;
  limite?: { usado: number; limite: number; restantes: number | null; ilimitado: boolean };
  meta_diaria?: { meta: number; total: number; batida_agora: boolean };
}

interface CadernoActionResp {
  id: number;
  questao_id?: number;
  adicionada?: boolean;
  total: number;
  nome?: string;
  redirect: string;
}

function formatTempo(s: number): string {
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export default function QuestaoPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <QuestaoScreen key={id} id={id} />;
}

function QuestaoScreen({ id }: { id: string }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const questaoId = Number(id);

  const [respostaQid, setRespostaQid] = useState<number | null>(null);
  const [respostaState, setRespostaState] = useState<{
    selecionada: string | null;
    resolvida: boolean;
    acertou: boolean | null;
  }>({ selecionada: null, resolvida: false, acertou: null });
  const [fontSize, setFontSize] = useState(16);
  const [showAtalhos, setShowAtalhos] = useState(false);
  const [forumAberto, setForumAberto] = useState(false);
  const [forumProfAberto, setForumProfAberto] = useState(false);
  const [cadernoOpen, setCadernoOpen] = useState(false);
  const [paywall, setPaywall] = useState<string | null>(null);
  const [tempo, setTempo] = useState(0);
  const [pausado, setPausado] = useState(false);
  const startedAt = useRef<number>(0);

  const { data: sessao } = useSession();
  const meuRole = (sessao?.user as { role?: string } | undefined)?.role ?? "user";
  const souProfOuAdmin = meuRole === "professor" || meuRole === "admin";

  const { data: questao, isPending, isError } = useQuery<Questao>({
    queryKey: qk.questao(id),
    queryFn: () => apiJson<Questao>(`/api/q/${id}`),
    staleTime: 60_000,
  });

  useEffect(() => {
    startedAt.current = Date.now();
  }, []);

  useEffect(() => {
    if (pausado) return;
    const timer = setInterval(() => setTempo((t) => t + 1), 1000);
    return () => clearInterval(timer);
  }, [pausado]);

  const respostaServidor = questao?.minha_resolucao ?? null;
  const respostaAtual =
    respostaQid === (questao?.id ?? null)
      ? respostaState
      : respostaServidor
        ? {
            selecionada: respostaServidor.resposta,
            resolvida: true,
            acertou: respostaServidor.acertou,
          }
        : { selecionada: null, resolvida: false, acertou: null };
  const { selecionada, resolvida, acertou } = respostaAtual;

  const anulada = questao?.status === "ANULADA" || (questao?.gabarito ?? "").toUpperCase().includes("ANULADA");
  const temFlagCorreta = questao?.alternativas.some((a) => a.correta === true) ?? false;
  const ehCorreta = (alt: Alternativa) =>
    temFlagCorreta ? alt.correta === true : alt.letra === questao?.gabarito;
  const altCorreta = questao?.alternativas.find(ehCorreta);
  const gabaritoLabel = temFlagCorreta
    ? `${altCorreta?.letra ?? "?"} (${(altCorreta?.texto_md || "").replace(/<[^>]+>/g, "").trim() || questao?.gabarito})`
    : questao?.gabarito;

  const responderMutation = useMutation({
    mutationFn: ({ qid, resposta, tempoSegundos }: { qid: number; resposta: string; tempoSegundos: number }) =>
      apiPost<ResponderResp>(`/api/q/${qid}/responder`, {
        resposta,
        tempo_segundos: tempoSegundos,
        caderno_id: null,
      }),
    onSuccess: (data) => {
      setRespostaState((prev) => ({ ...prev, acertou: data.acertou }));
      if (data.meta_diaria?.batida_agora) {
        celebrarMetaDiaria();
        toast.success("Meta diária batida!", {
          description: "Voce resolveu 15 questoes hoje.",
        });
      }
      void queryClient.invalidateQueries({ queryKey: qk.questao(id) });
      void queryClient.invalidateQueries({ queryKey: qk.limite() });
      void queryClient.invalidateQueries({ queryKey: qk.dashboard() });
    },
    onError: (err) => {
      setRespostaState((prev) => ({ ...prev, resolvida: false }));
      if (err instanceof ApiError && err.isLimite) {
        setPaywall(err.message || "Voce atingiu o limite de questoes de hoje do plano gratis.");
        return;
      }
      toast.error("Nao foi possivel registrar sua resposta.");
    },
  });

  const favoritarMutation = useMutation({
    mutationFn: (qid: number) => apiPost<{ questao_id: number; favorita: boolean }>(`/api/q/${qid}/favoritar`),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: qk.questao(id) });
      const anterior = queryClient.getQueryData<Questao>(qk.questao(id));
      queryClient.setQueryData<Questao>(qk.questao(id), (old) =>
        old ? { ...old, favorita: !old.favorita } : old,
      );
      return { anterior };
    },
    onError: (_err, _qid, ctx) => {
      if (ctx?.anterior) queryClient.setQueryData(qk.questao(id), ctx.anterior);
      toast.error("Nao foi possivel alterar a favorita.");
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: qk.questao(id) });
      void queryClient.invalidateQueries({ queryKey: qk.favoritas() });
    },
  });

  const resolverQuestao = useCallback(() => {
    if (!questao || !selecionada || resolvida || anulada) return;
    const tempoSegundos = Math.round((Date.now() - startedAt.current) / 1000);
    setRespostaQid(questao.id);
    setRespostaState((prev) => ({ ...prev, resolvida: true }));
    responderMutation.mutate({ qid: questao.id, resposta: selecionada, tempoSegundos });
  }, [anulada, questao, resolvida, responderMutation, selecionada]);

  const toggleFavorita = useCallback(() => {
    if (!questao) return;
    favoritarMutation.mutate(questao.id);
  }, [favoritarMutation, questao]);

  useHotkeys({
    ArrowLeft: () => router.push(`/q/questao/${Math.max(1, questaoId - 1)}`),
    ArrowRight: () => router.push(`/q/questao/${questaoId + 1}`),
    l: () => router.push(`/q/filtrar?aleatoria=1`),
    n: () => router.push(`/q/filtrar?status=nao-resolvidas`),
    z: () => router.back(),
    x: () => router.push(`/q/questao/${questaoId + 1}`),
    v: () => toast.info("Use a busca para filtrar suas questoes favoritas."),
    u: () => toast.info("Anotacoes ficam disponiveis dentro dos cadernos."),
    p: () => {
      const num = window.prompt("Ir para questao numero:");
      if (num) router.push(`/q/questao/${num}`);
    },
    m: toggleFavorita,
    j: toggleFavorita,
    w: () => toast.info("Anotacoes ficam disponiveis dentro dos cadernos."),
    o: () => { setForumProfAberto((v) => !v); setForumAberto(false); },
    f: () => { setForumAberto((v) => !v); setForumProfAberto(false); },
    h: () => toast.info("As estatisticas detalhadas ficam disponiveis dentro dos cadernos."),
    i: () => setShowAtalhos(true),
    y: () => toast.info("Texto associado indisponivel para esta questao."),
    q: () => setCadernoOpen(true),
    "+": () => setFontSize((s) => Math.min(s + 2, 28)),
    "=": () => setFontSize((s) => Math.min(s + 2, 28)),
    "-": () => setFontSize((s) => Math.max(s - 2, 12)),
    "0": () => setFontSize(16),
    ".": () => setPausado((p) => !p),
    "?": () => setShowAtalhos(true),
    Escape: () => {
      setForumAberto(false);
      setForumProfAberto(false);
      setCadernoOpen(false);
      setShowAtalhos(false);
    },
  });

  if (isPending) return <QuestaoSkeleton />;
  if (isError || !questao) {
    return (
      <div className="min-h-screen bg-page p-8 text-fg">
        <div className="mx-auto max-w-3xl rounded border border-error/30 bg-error/10 p-4 text-sm text-error">
          Nao foi possivel carregar esta questao.
        </div>
      </div>
    );
  }

  const tbBtn =
    "relative inline-flex h-8 w-8 items-center justify-center rounded transition hover:bg-surface-2 active:scale-90";
  const tbOn = "bg-primary/15 text-primary ring-1 ring-inset ring-primary";

  return (
    <div className="min-h-screen bg-page text-fg" style={{ fontSize }}>
      <div className="sticky top-0 z-20 flex items-center gap-3 border-b border-border/60 bg-page px-6 py-2 text-xs">
        <button onClick={() => router.push("/q/filtrar")} className="text-fg-faint hover:text-primary hover:underline">
          Questoes
        </button>
        <span className="text-fg-faint">/</span>
        <span className="truncate text-fg-muted">Questao avulsa #{questao.id}</span>
        <button
          onClick={() => router.push("/q/filtrar")}
          className="ml-auto text-fg-muted hover:text-fg"
          title="Voltar"
        >
          x
        </button>
        <button
          type="button"
          onClick={() => setPausado((p) => !p)}
          className="font-mono text-primary hover:underline"
          title="Pausar relogio (.)"
        >
          {formatTempo(tempo)}{pausado && " pause"}
        </button>
      </div>

      <main className="mx-auto max-w-5xl px-6 py-4">
        <section className="relative mb-4 rounded-lg border border-border/60 bg-surface">
          <header className="flex items-center gap-4 border-b border-border/60 px-4 py-3">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-cyan-600 to-violet-600 text-xl">
              {questao.banca?.sigla?.slice(0, 2).toUpperCase() || "?"}
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2 font-semibold">
                Questao <span className="text-primary">#{questao.id}</span>
                {questao.id_externo && <span className="font-mono text-xs text-fg-faint">TC {questao.id_externo}</span>}
                {questao.status === "ANULADA" && (
                  <span className="rounded border border-warning/40 bg-warning/15 px-2 py-0.5 text-[10px] font-semibold text-warning">
                    ANULADA
                  </span>
                )}
                {questao.favorita && <span className="text-yellow-400">★</span>}
              </div>
              <div className="mt-0.5 text-xs text-fg-muted">
                <span className="text-fg-faint">Materia:</span>{" "}
                <a href={`/q/filtrar?materia=${encodeURIComponent(questao.materia?.nome || "")}`} className="text-primary hover:underline">
                  {questao.materia?.nome || "Sem classificacao"}
                </a>
                <br />
                <span className="text-fg-faint">Assunto:</span>{" "}
                {questao.assuntos.length > 0 ? questao.assuntos.map((a, i) => (
                  <span key={`${a.id ?? a.nome}-${i}`}>
                    {i > 0 && ", "}
                    <a href={`/q/filtrar?assunto=${encodeURIComponent(a.nome)}`} className="text-primary hover:underline">
                      {a.nome}
                    </a>
                  </span>
                )) : <span className="text-fg-faint">Sem classificacao</span>}
              </div>
            </div>

            <div className="flex min-w-0 flex-1 flex-wrap items-center justify-end gap-2 text-lg text-fg-faint">
              <button
                title="Forum dos professores (O)"
                aria-pressed={forumProfAberto}
                onClick={() => { setForumProfAberto((v) => !v); setForumAberto(false); }}
                className={`${tbBtn} ${forumProfAberto ? tbOn : ""}`}
              >
                🎓
                {(questao.forum_count_professores ?? 0) > 0 && (
                  <span className="absolute -right-1 -top-1 rounded-full bg-secondary px-1 text-[10px] font-bold leading-tight text-black">
                    {questao.forum_count_professores}
                  </span>
                )}
              </button>
              <button
                title="Forum (F)"
                aria-pressed={forumAberto}
                onClick={() => { setForumAberto((v) => !v); setForumProfAberto(false); }}
                className={`${tbBtn} ${forumAberto ? tbOn : ""}`}
              >
                💬
                {(questao.forum_count ?? 0) > 0 && (
                  <span className="absolute -right-1 -top-1 rounded-full bg-primary px-1 text-[10px] font-bold leading-tight text-black">
                    {questao.forum_count}
                  </span>
                )}
              </button>
              <button
                title="Favoritar (M)"
                aria-pressed={questao.favorita}
                onClick={toggleFavorita}
                className={`${tbBtn} ${questao.favorita ? "bg-yellow-400/15 text-yellow-400 ring-1 ring-inset ring-yellow-400/70" : ""}`}
              >
                {questao.favorita ? "★" : "☆"}
              </button>
              <button
                title="Adicionar a caderno (Q)"
                onClick={() => setCadernoOpen(true)}
                className={tbBtn}
              >
                +
              </button>
              <button title="Atalhos (?)" onClick={() => setShowAtalhos(true)} className={tbBtn}>
                ?
              </button>
            </div>
          </header>

          {forumAberto && (
            <ForumPanel questaoId={questao.id} quadro="alunos" podeEscrever onFechar={() => setForumAberto(false)} />
          )}
          {forumProfAberto && (
            <ForumPanel
              questaoId={questao.id}
              quadro="professores"
              podeEscrever={souProfOuAdmin}
              onFechar={() => setForumProfAberto(false)}
            />
          )}

          <div className="flex items-center gap-2 border-b border-border/60 bg-surface-2 px-4 py-2 text-xs">
            <span className="font-semibold text-fg">{questao.banca?.sigla || "Banca"}</span>
            <span className="text-fg-faint">-</span>
            <span className="text-fg-muted">
              {[questao.cargo?.ano, questao.cargo?.nome, questao.orgao?.sigla].filter(Boolean).join(" / ") || "Dados da prova indisponiveis"}
            </span>
            {questao.cadernos.length > 0 && (
              <span className="ml-auto rounded border border-primary/30 bg-primary/10 px-2 py-0.5 text-primary">
                Em {questao.cadernos.length} caderno{questao.cadernos.length > 1 ? "s" : ""}
              </span>
            )}
          </div>

          <div className="p-5">
            <QuestionHtml
              as="article"
              className="prose prose-invert prose-cyan mb-4 max-w-none"
              html={questao.enunciado_html || questao.enunciado_md || ""}
            />

            <ol className="mb-5 space-y-1.5">
              {questao.alternativas.map((alt) => {
                const isCorreta = resolvida && ehCorreta(alt);
                const isErrada = resolvida && selecionada === alt.letra && !ehCorreta(alt);
                return (
                  <li key={alt.id}>
                    <button
                      type="button"
                      onClick={() => {
                        if (resolvida || anulada) return;
                        setRespostaQid(questao.id);
                        setRespostaState({ selecionada: alt.letra, resolvida: false, acertou: null });
                      }}
                      disabled={resolvida || anulada}
                      className={`flex w-full items-start gap-3 rounded border px-3 py-2 text-left transition ${
                        isCorreta ? "border-success bg-success/10" :
                        isErrada ? "border-error bg-error/10" :
                        selecionada === alt.letra ? "border-primary bg-primary/10" :
                        "border-border hover:bg-surface-2/40"
                      }`}
                    >
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-2 text-sm font-semibold">
                        {alt.letra}
                      </span>
                      <QuestionHtml as="span" className="flex-1" html={alt.texto_html || alt.texto_md || ""} />
                    </button>
                  </li>
                );
              })}
            </ol>

            {!resolvida && !anulada && (
              <button
                type="button"
                onClick={resolverQuestao}
                disabled={!selecionada || responderMutation.isPending}
                className="rounded bg-green-600 px-6 py-2 text-sm font-semibold uppercase tracking-wide text-white hover:bg-green-500 disabled:cursor-not-allowed disabled:bg-surface-2 disabled:text-fg-faint"
              >
                {responderMutation.isPending ? "Registrando..." : "Resolver Questao"}
              </button>
            )}

            {anulada && (
              <div className="rounded border border-warning/40 bg-warning/15 p-3 text-sm font-medium text-warning">
                Questao anulada - nao pode ser respondida e nao conta na sua estatistica.
              </div>
            )}

            {resolvida && acertou !== null && (
              <div className={`rounded p-3 text-sm font-medium ${
                acertou ? "border border-success/40 bg-success/15 text-success" :
                "border border-error/40 bg-error/15 text-error"
              }`}>
                {acertou ? "Voce acertou." : `Resposta esperada: ${gabaritoLabel}`}
              </div>
            )}

            {paywall && (
              <div className="mt-3 rounded border border-warning/40 bg-warning/15 p-3 text-sm text-warning">
                {paywall}
              </div>
            )}

            <nav className="mt-6 flex flex-wrap items-center gap-1 border-t border-border/60 pt-4">
              <NavBtn icon="←" title="Anterior (←)" onClick={() => router.push(`/q/questao/${Math.max(1, questao.id - 1)}`)} />
              <NavBtn icon="→" title="Proxima (→)" onClick={() => router.push(`/q/questao/${questao.id + 1}`)} />
              <NavBtn icon="★" title="Favoritar (M)" onClick={toggleFavorita} active={questao.favorita} />
              <NavBtn icon="+" title="Adicionar a caderno (Q)" onClick={() => setCadernoOpen(true)} />
              <NavBtn icon="💬" title="Forum (F)" onClick={() => { setForumAberto((v) => !v); setForumProfAberto(false); }} active={forumAberto} />
              <NavBtn icon="🎓" title="Forum dos professores (O)" onClick={() => { setForumProfAberto((v) => !v); setForumAberto(false); }} active={forumProfAberto} />
              <button onClick={() => setShowAtalhos(true)} className="ml-auto text-xs text-primary hover:underline">
                Lista das teclas de atalho
              </button>
            </nav>
          </div>
        </section>
      </main>

      {cadernoOpen && (
        <CadernoModal
          questao={questao}
          onClose={() => setCadernoOpen(false)}
          onCreated={(redirect) => router.push(redirect)}
        />
      )}

      {showAtalhos && <AtalhosModal onClose={() => setShowAtalhos(false)} />}
    </div>
  );
}

function CadernoModal({
  questao,
  onClose,
  onCreated,
}: {
  questao: Questao;
  onClose: () => void;
  onCreated: (redirect: string) => void;
}) {
  const queryClient = useQueryClient();
  const [nome, setNome] = useState(`Questao ${questao.id} - ${questao.materia?.nome || questao.banca?.sigla || "studIA"}`);
  const jaTem = new Set(questao.cadernos.map((c) => c.id));

  const { data: cadernos, isPending, isError } = useQuery<CadernoResumo[]>({
    queryKey: qk.cadernos(null),
    queryFn: () => apiJson<CadernoResumo[]>("/api/q/cadernos"),
    staleTime: 30_000,
  });

  const criar = useMutation({
    mutationFn: () =>
      apiPost<CadernoActionResp>("/api/q/cadernos", {
        nome: nome.trim() || `Questao ${questao.id}`,
        pasta: questao.materia?.nome ?? null,
        question_ids: [questao.id],
      }),
    onSuccess: (data) => {
      toast.success("Caderno criado.");
      void queryClient.invalidateQueries({ queryKey: qk.cadernos(null) });
      void queryClient.invalidateQueries({ queryKey: qk.questao(questao.id) });
      onCreated(data.redirect);
    },
    onError: () => toast.error("Nao foi possivel criar o caderno."),
  });

  const adicionar = useMutation({
    mutationFn: (cadernoId: number) =>
      apiPost<CadernoActionResp>(`/api/q/cadernos/${cadernoId}/questoes/${questao.id}`),
    onSuccess: (data) => {
      toast.success(data.adicionada ? "Questao adicionada ao caderno." : "Esta questao ja estava no caderno.");
      void queryClient.invalidateQueries({ queryKey: qk.cadernos(null) });
      void queryClient.invalidateQueries({ queryKey: qk.questao(questao.id) });
      onClose();
    },
    onError: () => toast.error("Nao foi possivel adicionar ao caderno."),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4" onClick={onClose}>
      <div
        className="w-full max-w-2xl rounded-lg border border-border bg-surface p-5 shadow-2xl"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-semibold text-fg">Adicionar a caderno</h2>
            <p className="mt-1 text-sm text-fg-muted">Questao #{questao.id}</p>
          </div>
          <button onClick={onClose} className="rounded px-2 py-1 text-fg-faint hover:bg-surface-2 hover:text-fg">
            x
          </button>
        </div>

        <div className="grid gap-4 md:grid-cols-[1fr_1.2fr]">
          <section className="rounded border border-border/60 p-3">
            <label className="mb-2 block text-xs font-semibold uppercase tracking-wide text-fg-faint">
              Novo caderno
            </label>
            <input
              value={nome}
              onChange={(event) => setNome(event.target.value)}
              className="w-full rounded border border-border bg-page px-3 py-2 text-sm text-fg outline-none focus:border-primary"
            />
            <button
              type="button"
              onClick={() => criar.mutate()}
              disabled={criar.isPending}
              className="mt-3 w-full rounded bg-primary px-3 py-2 text-sm font-semibold text-black hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {criar.isPending ? "Criando..." : "Comecar caderno"}
            </button>
          </section>

          <section className="rounded border border-border/60 p-3">
            <div className="mb-2 text-xs font-semibold uppercase tracking-wide text-fg-faint">
              Cadernos existentes
            </div>
            <div className="max-h-64 space-y-2 overflow-y-auto pr-1">
              {isPending && [0, 1, 2].map((i) => <Skeleton key={i} className="h-11 w-full" />)}
              {isError && <p className="text-sm text-error">Nao foi possivel carregar seus cadernos.</p>}
              {!isPending && !isError && (cadernos ?? []).length === 0 && (
                <p className="text-sm text-fg-faint">Nenhum caderno encontrado.</p>
              )}
              {!isPending && !isError && (cadernos ?? []).map((caderno) => {
                const contem = jaTem.has(caderno.id);
                return (
                  <button
                    key={caderno.id}
                    type="button"
                    disabled={contem || adicionar.isPending}
                    onClick={() => adicionar.mutate(caderno.id)}
                    className="flex w-full items-center justify-between gap-3 rounded border border-border/60 px-3 py-2 text-left text-sm hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    <span className="min-w-0">
                      <span className="block truncate font-medium text-fg">{caderno.nome}</span>
                      <span className="block truncate text-xs text-fg-faint">
                        {caderno.pasta || "Sem classificacao"} {typeof caderno.total === "number" ? `- ${caderno.total} questoes` : ""}
                      </span>
                    </span>
                    <span className="shrink-0 text-xs text-primary">{contem ? "Ja contem" : "Adicionar"}</span>
                  </button>
                );
              })}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

function QuestaoSkeleton() {
  return (
    <div className="min-h-screen bg-page text-fg">
      <div className="border-b border-border/60 px-6 py-2">
        <Skeleton className="h-5 w-80" />
      </div>
      <main className="mx-auto max-w-5xl px-6 py-4">
        <section className="rounded-lg border border-border/60 bg-surface">
          <header className="flex items-center gap-4 border-b border-border/60 px-4 py-3">
            <Skeleton className="h-12 w-12 rounded-full" />
            <div className="flex-1 space-y-2">
              <Skeleton className="h-4 w-60" />
              <Skeleton className="h-3 w-96" />
            </div>
            <Skeleton className="h-8 w-40" />
          </header>
          <div className="space-y-4 p-5">
            <Skeleton className="h-4 w-full" />
            <Skeleton className="h-4 w-11/12" />
            <Skeleton className="h-4 w-4/5" />
            {[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-12 w-full" />)}
            <Skeleton className="h-10 w-44" />
          </div>
        </section>
      </main>
    </div>
  );
}

function NavBtn({
  icon,
  title,
  onClick,
  active = false,
}: {
  icon: string;
  title: string;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={onClick}
      aria-pressed={active}
      className={`flex h-8 min-w-8 items-center justify-center rounded border border-border px-2 text-sm transition hover:bg-surface-2 active:scale-95 ${
        active ? "bg-primary/15 text-primary ring-1 ring-inset ring-primary" : "text-fg-muted"
      }`}
    >
      {icon}
    </button>
  );
}

function AtalhosModal({ onClose }: { onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 px-4" onClick={onClose}>
      <div
        className="max-h-[80vh] w-full max-w-2xl overflow-y-auto rounded-lg border border-border bg-surface p-6"
        onClick={(event) => event.stopPropagation()}
      >
        <h2 className="mb-4 text-lg font-semibold">Lista das teclas de atalho</h2>
        {(["nav", "acao", "ui"] as const).map((grupo) => (
          <div key={grupo} className="mb-4">
            <h3 className="mb-2 text-xs uppercase tracking-wider text-primary">
              {grupo === "nav" ? "Navegacao" : grupo === "acao" ? "Acoes" : "Interface"}
            </h3>
            <table className="w-full text-sm">
              <tbody>
                {Object.entries(ATALHOS_TC)
                  .filter(([, value]) => value.group === grupo)
                  .map(([key, value]) => (
                    <tr key={key}>
                      <td className="py-1 pr-4 font-mono text-primary">{key}</td>
                      <td className="py-1 text-fg">{value.label}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ))}
        <button onClick={onClose} className="mt-4 text-xs text-fg-muted hover:text-fg-strong">
          Fechar
        </button>
      </div>
    </div>
  );
}

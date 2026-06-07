"use client";

import { use, useCallback, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useHotkeys, ATALHOS_TC } from "../../../hooks/useHotkeys";
import type { CanvasTool, StrikeTarget } from "./annotations/types";
import { useQuestionAnnotations } from "./annotations/useQuestionAnnotations";
import { CanvasToolbar } from "./components/CanvasToolbar";
import { QuestionCanvasOverlay } from "./components/QuestionCanvasOverlay";
import { ScientificCalculator } from "./components/ScientificCalculator";
import { StrikableAlternative } from "./components/StrikableAlternative";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8011";

interface Alternativa {
  id: number;
  letra: string;
  texto_md: string;
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
}

interface Caderno {
  id: number;
  nome: string;
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
  const [caderno, setCaderno] = useState<Caderno | null>(null);
  const [idx, setIdx] = useState(0);
  const [questao, setQuestao] = useState<Questao | null>(null);
  const [stats, setStats] = useState<Stats>({ resolvidas: 0, acertos: 0, erros: 0 });
  const [selecionada, setSelecionada] = useState<string | null>(null);
  const [resolvida, setResolvida] = useState(false);
  const [acertou, setAcertou] = useState<boolean | null>(null);
  const [fav, setFav] = useState(false);
  const [showAtalhos, setShowAtalhos] = useState(false);
  const [fontSize, setFontSize] = useState(16);
  const [tab, setTab] = useState<Tab>("Questoes");
  const [tempo, setTempo] = useState(0);
  const [pausado, setPausado] = useState(false);
  const [modoLeitura, setModoLeitura] = useState(false);
  const [canvasActive, setCanvasActive] = useState(false);
  const [canvasTool, setCanvasTool] = useState<CanvasTool>("pen");
  const [canvasColor, setCanvasColor] = useState("#22c55e");
  const [canvasWidth, setCanvasWidth] = useState(5);
  const [calculatorOpen, setCalculatorOpen] = useState(false);
  const questionCardRef = useRef<HTMLDivElement | null>(null);
  const startedAt = useRef<number>(0);

  // Timer global (geral do caderno) + init de startedAt
  useEffect(() => {
    startedAt.current = Date.now();
  }, []);

  useEffect(() => {
    if (pausado) return;
    const t = setInterval(() => setTempo((x) => x + 1), 1000);
    return () => clearInterval(t);
  }, [pausado]);

  // Contador do cabeçalho = acumulado do CADERNO (não da questão isolada).
  const carregarStatsCaderno = useCallback(() => {
    fetch(`${API}/api/q/cadernos/${id}/estatisticas`)
      .then((r) => r.json())
      .then((s) => setStats({ resolvidas: s.resolvidas, acertos: s.acertos, erros: s.erros }))
      .catch(console.error);
  }, [id]);

  useEffect(() => {
    fetch(`${API}/api/q/cadernos/${id}`)
      .then((r) => r.json())
      .then(setCaderno)
      .catch(console.error);
    carregarStatsCaderno();
  }, [id, carregarStatsCaderno]);

  const currentQid = caderno?.question_ids[idx];
  const annotations = useQuestionAnnotations(caderno?.id ?? null, currentQid ?? null);

  useEffect(() => {
    if (!currentQid) return;
    let cancelled = false;
    startedAt.current = Date.now();
    fetch(`${API}/api/q/${currentQid}`)
      .then((r) => r.json())
      .then((q) => {
        if (cancelled) return;
        setQuestao(q);
        setSelecionada(null);
        setResolvida(false);
        setAcertou(null);
      })
      .catch(console.error);
    return () => { cancelled = true; };
  }, [currentQid]);

  async function resolverQuestao() {
    if (!selecionada || !questao || !caderno) return;
    const tempo_segundos = Math.round((Date.now() - startedAt.current) / 1000);
    setResolvida(true);
    try {
      const r = await fetch(`${API}/api/q/${questao.id}/responder`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resposta: selecionada, tempo_segundos, caderno_id: caderno.id }),
      });
      const data = await r.json();
      setAcertou(data.acertou);
      carregarStatsCaderno();
    } catch (e) {
      console.error(e);
    }
  }

  function avancar(delta: number) {
    if (!caderno) return;
    void annotations.flush();
    const novo = Math.max(0, Math.min(caderno.total - 1, idx + delta));
    setIdx(novo);
  }

  function aleatoria() {
    if (!caderno) return;
    void annotations.flush();
    setIdx(Math.floor(Math.random() * caderno.total));
  }

  useHotkeys({
    ArrowLeft: () => { if (!canvasActive) avancar(-1); },
    ArrowRight: () => { if (!canvasActive) avancar(1); },
    l: () => { if (!canvasActive) aleatoria(); },
    n: () => { if (!canvasActive) avancar(1); },
    p: () => {
      if (canvasActive) return;
      const num = prompt(`Ir para questão (1 a ${caderno?.total}):`);
      if (num && /^\d+$/.test(num)) {
        const n = Math.min(Math.max(parseInt(num), 1), caderno?.total || 1) - 1;
        void annotations.flush();
        setIdx(n);
      }
    },
    m: () => { if (!canvasActive) setFav((f) => !f); },
    j: () => { if (!canvasActive) setFav((f) => !f); },
    k: () => setModoLeitura((m) => !m),
    "+": () => setFontSize((s) => Math.min(28, s + 2)),
    "=": () => setFontSize((s) => Math.min(28, s + 2)),
    "-": () => setFontSize((s) => Math.max(12, s - 2)),
    "0": () => setFontSize(16),
    ".": () => setPausado((p) => !p),
    "?": () => setShowAtalhos(true),
    Escape: () => setCanvasActive(false),
  }, { enabled: !calculatorOpen });

  if (!caderno) return <div className="p-8 text-gray-400">Carregando caderno…</div>;
  if (!questao) return <div className="p-8 text-gray-400">Carregando questão {idx + 1} de {caderno.total}…</div>;

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
      className={`min-h-screen ${modoLeitura ? "bg-amber-50 text-gray-900" : "bg-[#121212] text-gray-200"}`}
      style={{ fontSize }}
    >
      {/* ─── Top breadcrumb + timer ─── */}
      <div className="border-b border-gray-700/60 px-6 py-2 flex items-center gap-3 text-xs sticky top-0 bg-[#0f0f0f] z-20">
        <span className="text-gray-500">Estudo</span>
        <span className="text-gray-600">›</span>
        <span className="text-gray-500">Minhas pastas</span>
        <span className="text-gray-600">›</span>
        <span className="text-gray-400">{caderno.nome}</span>
        <button
          onClick={() => router.push("/q/filtrar")}
          className="ml-auto text-gray-400 hover:text-gray-200"
          title="Voltar"
        >
          ✕
        </button>
        <div className="flex items-center gap-2 text-cyan-400 font-mono">
          <span title="Modo leitura (K)" className="cursor-pointer" onClick={() => setModoLeitura((m) => !m)}>
            👁
          </span>
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
      <nav className="border-b border-gray-700/60 px-6 flex items-center gap-1 text-sm sticky top-[36px] bg-[#0f0f0f] z-10">
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
                ? "border-cyan-500 text-cyan-400"
                : "border-transparent text-gray-400 hover:text-gray-200"
            }`}
          >
            {label}
          </button>
        ))}
        <button className="ml-auto px-4 py-2.5 text-cyan-400 hover:underline text-xs">
          🔗 Compartilhar
        </button>
      </nav>

      {tab === "Estatisticas" && (
        <EstatisticasTab cadernoId={caderno.id} />
      )}
      {tab === "Indice" && (
        <IndiceTab
          cadernoId={caderno.id}
          onAbrir={(n) => {
            void annotations.flush();
            setIdx(n - 1);
            setTab("Questoes");
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
          modoLeitura={modoLeitura} setModoLeitura={setModoLeitura}
          pausado={pausado} setPausado={setPausado}
          tempo={tempo}
        />
      )}
      {tab === "Imprimir" && (
        <div className="max-w-4xl mx-auto px-6 py-8 text-sm text-gray-500 italic">
          Aba &quot;Imprimir&quot; — gera PDF do caderno (em breve via /api/q/cadernos/{caderno.id}/pdf).
        </div>
      )}

      {tab === "Questoes" && (
      <main className="max-w-5xl mx-auto px-6 py-4">
        {/* ─── Card stats da questão ─── */}
        <div ref={questionCardRef} className="relative mb-4 rounded-lg border border-gray-700/60 bg-[#1a1a1a]">
          <QuestionCanvasOverlay
            active={canvasActive}
            canvas={annotations.canvas}
            tool={canvasTool}
            color={canvasColor}
            width={canvasWidth}
            onChange={annotations.updateCanvas}
          />
          <header className="px-4 py-3 flex items-center gap-4 border-b border-gray-700/60">
            <div className="w-12 h-12 rounded-full bg-gradient-to-br from-cyan-600 to-violet-600 flex items-center justify-center text-xl shrink-0">
              {questao.banca?.sigla?.slice(0, 2).toUpperCase() || "TC"}
            </div>
            <div className="flex-1 min-w-0">
              <div className="font-semibold flex items-center gap-2 flex-wrap">
                Questão <span className="text-cyan-400">{idx + 1}</span> de {caderno.total}
                <span className="text-xs font-normal">
                  (<span className="text-cyan-400">{stats.resolvidas}</span> Resolvidas,{" "}
                  <span className="text-green-400">{stats.acertos}</span> Acertos e{" "}
                  <span className="text-red-400">{stats.erros}</span> Erros{stats.resolvidas > 0 && `, ${taxa}% acerto`}) ✕
                </span>
                {fav && <span className="text-yellow-400">⭐</span>}
              </div>
              <div className="text-xs text-gray-400 mt-0.5">
                <span className="text-gray-500">Matéria:</span>{" "}
                <a href={`/q/filtrar?materia=${encodeURIComponent(questao.materia?.nome || "")}`} className="text-cyan-400 hover:underline">
                  {questao.materia?.nome}
                </a>
                <br />
                <span className="text-gray-500">Assunto:</span>{" "}
                {questao.assuntos.map((a, i) => (
                  <span key={a.id}>
                    {i > 0 && ", "}
                    <a href={`/q/filtrar?assunto=${encodeURIComponent(a.nome)}`} className="text-cyan-400 hover:underline">
                      {a.nome}
                    </a>
                  </span>
                ))}
                {questao.assuntos.length === 0 && <span className="text-gray-600">Sem classificação</span>}
              </div>
            </div>
            <div className="flex flex-wrap items-center justify-end gap-2 text-lg text-gray-500">
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
              <button title="Comentário (O)" className="hover:text-cyan-400">🎓</button>
              <button title="Teoria" className="hover:text-cyan-400">📕</button>
              <button title="Fórum (F)" className="hover:text-cyan-400">💬</button>
              <button title="Favoritar (M)" onClick={() => setFav((f) => !f)} className={fav ? "text-yellow-400" : "hover:text-yellow-400"}>
                {fav ? "★" : "☆"}
              </button>
              <button title="Anotação (W)" className="hover:text-cyan-400">✏️</button>
              <button title="Estatísticas" className="hover:text-cyan-400">⭕</button>
              <button title="Mais opções" className="hover:text-cyan-400">⋮</button>
            </div>
          </header>

          {/* ─── Linha enxuta com código + banca ─── */}
          <div className="px-4 py-2 bg-[#151515] border-b border-gray-700/60 text-xs flex items-center gap-2">
            <span className="text-gray-500">🔗</span>
            <span className="text-cyan-400 font-mono">#{questao.id_externo}</span>
            <span className="font-semibold text-gray-300">{questao.banca?.sigla}</span>
            <span className="text-gray-500">-</span>
            <span className="text-gray-400">
              {questao.cargo?.ano} - {questao.cargo?.nome} / {questao.orgao?.sigla} / {questao.cargo?.ano}
            </span>
            {questao.status === "ANULADA" && (
              <span className="ml-2 px-2 py-0.5 bg-yellow-950 text-yellow-300 rounded text-[10px] font-semibold">ANULADA</span>
            )}
            <button className="ml-auto text-gray-500 hover:text-gray-300" title="Reportar erro">↗</button>
            <button className="text-gray-500 hover:text-gray-300" title="Anterior (←)" onClick={() => avancar(-1)}>←</button>
            <button className="text-gray-500 hover:text-gray-300" title="Próxima (→)" onClick={() => avancar(1)}>→</button>
          </div>

          {/* ─── Enunciado + alternativas ─── */}
          <div className="p-5">
            <article
              onDoubleClick={() => annotations.toggleStrike({ type: "statement-block", index: 0 })}
              className={`prose prose-invert prose-cyan max-w-none mb-4 ${
                isStruck({ type: "statement-block", index: 0 }) ? "text-gray-500 line-through decoration-red-500 decoration-2" : ""
              }`}
              title="Dois cliques riscam ou restauram o enunciado"
              dangerouslySetInnerHTML={{ __html: questao.enunciado_html }}
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
                      onSelect={() => setSelecionada(alt.letra)}
                      onToggleStrike={() => annotations.toggleStrike({ type: "alternative", id: alt.id })}
                      className={`w-full text-left flex items-start gap-3 px-3 py-2 rounded border transition ${
                        isCorreta ? "border-green-500 bg-green-950/40" :
                        isErrada ? "border-red-500 bg-red-950/40" :
                        selecionada === alt.letra ? "border-cyan-500 bg-cyan-950/40" :
                        "border-gray-700 hover:bg-gray-800/40"
                      }`}
                    >
                      <span className="flex-1" dangerouslySetInnerHTML={{ __html: alt.texto_md || "" }} />
                    </StrikableAlternative>
                  </li>
                );
              })}
            </ol>

            {!resolvida && (
              <button
                onClick={resolverQuestao}
                disabled={!selecionada}
                className="bg-green-600 hover:bg-green-500 disabled:bg-gray-700 disabled:cursor-not-allowed px-6 py-2 rounded font-semibold uppercase tracking-wide text-sm"
              >
                Resolver Questão
              </button>
            )}

            {resolvida && (
              <div className={`p-3 rounded text-sm font-medium ${
                acertou ? "bg-green-950 border border-green-700 text-green-300" :
                "bg-red-950 border border-red-700 text-red-300"
              }`}>
                {acertou ? "✓ Você acertou!" : `✗ Resposta esperada: ${gabaritoLabel}`}
              </div>
            )}

            {/* ─── Bottom nav (estilo TC) ─── */}
            <nav className="mt-6 pt-4 border-t border-gray-700/60 flex items-center gap-1 flex-wrap">
              <NavBtn icon="←" title="Anterior (←)" onClick={() => avancar(-1)} disabled={idx === 0} />
              <NavBtn icon="→" title="Próxima (→)" onClick={() => avancar(1)} disabled={idx === caderno.total - 1} />
              <NavBtn icon="🔀" title="Aleatória (L)" onClick={aleatoria} />
              <NavBtn icon="→⊟" title="Próxima não resolvida (N)" onClick={() => avancar(1)} />
              <NavBtn icon="◀" title="Tópico anterior (Z)" onClick={() => avancar(-1)} />
              <NavBtn icon="▶" title="Tópico seguinte (X)" onClick={() => avancar(1)} />
              <NavBtn icon="↺" title="Desfazer (Ctrl+Z)" onClick={() => avancar(-1)} />
              <NavBtn icon="★" title="Próxima favorita (V)" onClick={() => avancar(1)} />
              <NavBtn icon="✎" title="Próxima anotada (U)" onClick={() => avancar(1)} />

              <span className="ml-auto text-xs text-gray-500">{idx + 1} / {caderno.total}</span>
            </nav>

            <div className="mt-3 text-xs text-gray-500 flex items-center gap-1">
              <span className="text-red-500">⊘</span>
              <span>Encontrou algum erro nesta questão?</span>
              <button className="text-cyan-400 hover:underline">Fale conosco</button>
              <button onClick={() => setShowAtalhos(true)} className="ml-auto text-cyan-400 hover:underline">
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
          <div className="bg-[#1e1e1e] border border-gray-700 rounded-lg p-6 max-w-2xl w-full max-h-[80vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
            <h2 className="text-lg font-semibold mb-4">Atalhos de teclado</h2>
            {(["nav", "acao", "ui"] as const).map((grupo) => (
              <div key={grupo} className="mb-4">
                <h3 className="text-xs uppercase tracking-wider text-cyan-400 mb-2">
                  {grupo === "nav" ? "Navegação" : grupo === "acao" ? "Ações" : "Interface"}
                </h3>
                <table className="w-full text-sm">
                  <tbody>
                    {Object.entries(ATALHOS_TC)
                      .filter(([, v]) => v.group === grupo)
                      .map(([k, v]) => (
                        <tr key={k}>
                          <td className="py-1 pr-4 font-mono text-cyan-300">{k}</td>
                          <td className="py-1 text-gray-300">{v.label}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            ))}
            <button onClick={() => setShowAtalhos(false)} className="mt-4 text-xs text-gray-400 hover:text-gray-200">
              Fechar (Esc)
            </button>
          </div>
        </div>
      )}
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
      className="w-10 h-10 border border-gray-700 hover:bg-gray-800 disabled:opacity-30 rounded flex items-center justify-center text-base"
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

function EstatisticasTab({ cadernoId }: { cadernoId: number }) {
  const [data, setData] = useState<StatsDetalhe | null>(null);

  useEffect(() => {
    fetch(`${API}/api/q/cadernos/${cadernoId}/stats-detalhe`)
      .then((r) => r.json())
      .then(setData)
      .catch(console.error);
  }, [cadernoId]);

  if (!data) return <div className="p-8 text-gray-400">Carregando estatísticas…</div>;

  const progresso = data.questoes_total > 0 ? Math.round((data.resolvidas / data.questoes_total) * 100) : 0;

  return (
    <main className="max-w-5xl mx-auto px-6 py-6 space-y-6">
      {/* ─── Resumo grande ─── */}
      <section className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <Card label="Resolvidas" value={data.resolvidas} sub={`de ${data.questoes_total}`} color="cyan" />
        <Card label="Acertos" value={data.acertos} sub={`${data.taxa}% taxa`} color="green" />
        <Card label="Erros" value={data.erros} color="red" />
        <Card label="Tempo total" value={formatTempo(data.tempo_total_segundos)} mono color="violet" />
        <Card label="Médio/questão" value={data.tempo_medio_segundos > 0 ? `${Math.round(data.tempo_medio_segundos)}s` : "—"} color="amber" />
      </section>

      {/* ─── Barra de progresso do caderno ─── */}
      <section className="border border-gray-700/60 rounded-lg bg-[#1a1a1a] p-4">
        <div className="flex items-center justify-between mb-2 text-sm">
          <span className="text-gray-400">Progresso no caderno</span>
          <span className="text-cyan-400 font-semibold">{progresso}%</span>
        </div>
        <div className="h-3 bg-gray-800 rounded overflow-hidden">
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
        <section className="border border-gray-700/60 rounded-lg bg-[#1a1a1a] p-4">
          <h3 className="text-sm font-semibold mb-3 text-gray-300">Últimas 20 resoluções</h3>
          <table className="w-full text-xs">
            <thead className="text-gray-500 border-b border-gray-700/60">
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
                <tr key={i} className="border-b border-gray-800/60">
                  <td className="py-1.5 px-2 font-mono text-cyan-400">Q{r.id_externo}</td>
                  <td className="py-1.5 px-2 font-mono">{r.resposta}</td>
                  <td className={`py-1.5 px-2 ${r.acertou ? "text-green-400" : "text-red-400"}`}>
                    {r.acertou ? "✓ Acerto" : "✗ Erro"}
                  </td>
                  <td className="py-1.5 px-2 text-right text-gray-400">
                    {r.tempo_segundos ? `${r.tempo_segundos}s` : "—"}
                  </td>
                  <td className="py-1.5 px-2 text-right text-gray-500">
                    {new Date(r.created_at).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {data.resolvidas === 0 && (
        <div className="text-center py-12 text-gray-500 text-sm">
          Resolva algumas questões para ver suas estatísticas aqui.
        </div>
      )}
    </main>
  );
}

function Card({ label, value, sub, color, mono }: {
  label: string; value: string | number; sub?: string;
  color: "cyan" | "green" | "red" | "violet" | "amber";
  mono?: boolean;
}) {
  const colors = {
    cyan: "text-cyan-400",
    green: "text-green-400",
    red: "text-red-400",
    violet: "text-violet-400",
    amber: "text-amber-400",
  };
  return (
    <div className="border border-gray-700/60 rounded-lg bg-[#1a1a1a] p-4">
      <div className={`text-2xl font-bold ${colors[color]} ${mono ? "font-mono" : ""}`}>{value}</div>
      <div className="text-xs text-gray-400 mt-1">{label}</div>
      {sub && <div className="text-xs text-gray-500">{sub}</div>}
    </div>
  );
}

function BarBlock({ titulo, items }: {
  titulo: string;
  items: Array<{ nome: string; resolvidas: number; acertos: number; taxa: number }>;
}) {
  const max = Math.max(...items.map((i) => i.resolvidas), 1);
  return (
    <section className="border border-gray-700/60 rounded-lg bg-[#1a1a1a] p-4">
      <h3 className="text-sm font-semibold mb-3 text-gray-300">{titulo}</h3>
      <div className="space-y-2">
        {items.map((it) => (
          <div key={it.nome} className="text-xs">
            <div className="flex items-center justify-between mb-0.5">
              <span className="text-gray-300 truncate flex-1 mr-2">{it.nome}</span>
              <span className="text-gray-500 whitespace-nowrap">
                {it.acertos}/{it.resolvidas}
                <span className={`ml-2 font-semibold ${it.taxa >= 70 ? "text-green-400" : it.taxa >= 50 ? "text-amber-400" : "text-red-400"}`}>
                  {it.taxa}%
                </span>
              </span>
            </div>
            <div className="h-1.5 bg-gray-800 rounded overflow-hidden flex">
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
  const [items, setItems] = useState<IndiceItem[]>([]);
  const [filtro, setFiltro] = useState("");

  useEffect(() => {
    fetch(`${API}/api/q/cadernos/${cadernoId}/indice`)
      .then((r) => r.json())
      .then((d) => setItems(d.items || []))
      .catch(console.error);
  }, [cadernoId]);

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
          className="flex-1 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm focus:outline-none focus:border-cyan-500"
        />
        <span className="text-xs text-gray-500">{filtrados.length} / {items.length}</span>
      </div>

      <div className="border border-gray-700/60 rounded-lg overflow-hidden">
        <div className="max-h-[70vh] overflow-y-auto">
          {filtrados.map((it) => (
            <button
              key={it.questao_id}
              onClick={() => onAbrir(it.n)}
              className={`w-full text-left px-4 py-2.5 border-b border-gray-800/60 hover:bg-gray-800/40 flex items-start gap-3 ${
                it.n === idxAtual + 1 ? "bg-cyan-950/30 border-l-2 border-l-cyan-500" : ""
              }`}
            >
              <span className="font-mono text-xs text-gray-500 w-12 shrink-0 pt-0.5">#{it.n}</span>
              <div className="flex-1 min-w-0">
                <div className="text-xs text-gray-400 flex gap-2 mb-0.5">
                  <span className="text-cyan-400 font-mono">Q{it.id_externo}</span>
                  <span className="text-gray-600">·</span>
                  <span>{it.banca}</span>
                  <span className="text-gray-600">·</span>
                  <span className="truncate">{it.materia}</span>
                </div>
                <div className="text-xs text-gray-500 truncate">{it.preview}…</div>
              </div>
              <span className="font-mono text-xs text-gray-500 shrink-0 pt-0.5">
                {it.gabarito && (
                  <span className="bg-gray-800 px-1.5 py-0.5 rounded">
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
  const [items, setItems] = useState<GabaritoItem[]>([]);

  useEffect(() => {
    fetch(`${API}/api/q/cadernos/${cadernoId}/gabarito`)
      .then((r) => r.json())
      .then((d) => setItems(d.items || []))
      .catch(console.error);
  }, [cadernoId]);

  function corDe(g: string | null) {
    if (!g) return "text-gray-500";
    if (g.includes("ANULADA")) return "text-yellow-400 bg-yellow-950";
    if (g === "CERTO") return "text-green-400 bg-green-950";
    if (g === "ERRADO") return "text-red-400 bg-red-950";
    return "text-cyan-300 bg-cyan-950";
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
      <h3 className="text-sm font-semibold mb-3 text-gray-300">
        Gabarito do caderno ({items.length} questões)
      </h3>
      <div className="grid grid-cols-[repeat(auto-fill,minmax(64px,1fr))] gap-1.5">
        {items.map((it) => (
          <div
            key={it.n}
            className={`border border-gray-700/60 rounded p-1.5 text-center text-xs ${corDe(it.gabarito)}`}
            title={`Q${it.id_externo} — ${it.gabarito || "?"}`}
          >
            <div className="text-[10px] text-gray-500 font-mono mb-0.5">{it.n})</div>
            <div className="font-bold font-mono">{abrev(it.gabarito)}</div>
          </div>
        ))}
      </div>
    </main>
  );
}

// ════════════════════════════ CONFIGURAÇÕES ════════════════════════════

function ConfigTab({
  fontSize, setFontSize, modoLeitura, setModoLeitura, pausado, setPausado, tempo,
}: {
  fontSize: number; setFontSize: (n: number) => void;
  modoLeitura: boolean; setModoLeitura: (b: boolean) => void;
  pausado: boolean; setPausado: (b: boolean) => void;
  tempo: number;
}) {
  return (
    <main className="max-w-3xl mx-auto px-6 py-6 space-y-5">
      <div className="border border-gray-700/60 rounded-lg bg-[#1a1a1a] p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Cronômetro</h3>
        <div className="flex items-center gap-3">
          <div className="text-2xl font-mono text-cyan-400">{formatTempo(tempo)}</div>
          <button
            onClick={() => setPausado(!pausado)}
            className="bg-gray-800 hover:bg-gray-700 px-4 py-2 rounded text-sm"
          >
            {pausado ? "▶ Retomar" : "⏸ Pausar"} <span className="text-xs text-gray-500">(.)</span>
          </button>
        </div>
      </div>

      <div className="border border-gray-700/60 rounded-lg bg-[#1a1a1a] p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Tamanho da fonte</h3>
        <div className="flex items-center gap-3">
          <button onClick={() => setFontSize(Math.max(12, fontSize - 2))} className="w-10 h-10 border border-gray-700 rounded hover:bg-gray-800">−</button>
          <div className="font-mono text-cyan-400 w-14 text-center">{fontSize}px</div>
          <button onClick={() => setFontSize(Math.min(28, fontSize + 2))} className="w-10 h-10 border border-gray-700 rounded hover:bg-gray-800">+</button>
          <button onClick={() => setFontSize(16)} className="ml-3 text-xs text-gray-400 hover:text-gray-200 underline">Padrão (0)</button>
        </div>
      </div>

      <div className="border border-gray-700/60 rounded-lg bg-[#1a1a1a] p-4">
        <h3 className="text-sm font-semibold text-gray-300 mb-3">Modo leitura</h3>
        <label className="flex items-center gap-2 cursor-pointer">
          <input type="checkbox" checked={modoLeitura} onChange={(e) => setModoLeitura(e.target.checked)} />
          <span className="text-sm">Fundo claro (amber-50) para leitura prolongada</span>
          <span className="text-xs text-gray-500 ml-auto">Atalho (K)</span>
        </label>
      </div>

      <div className="border border-gray-700/60 rounded-lg bg-[#1a1a1a] p-4 text-xs text-gray-400 space-y-1">
        <div><strong className="text-gray-300">Modo de resolução:</strong> Sequencial (próximo idx)</div>
        <div><strong className="text-gray-300">Ordem das questões:</strong> Aleatória fixa (definida na criação)</div>
        <div><strong className="text-gray-300">Mostrar gabarito após responder:</strong> Sim</div>
      </div>
    </main>
  );
}

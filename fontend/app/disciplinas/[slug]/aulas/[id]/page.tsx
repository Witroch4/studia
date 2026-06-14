"use client";

import Link from "next/link";
import { useState, useEffect, use } from "react";
import MarkdownRenderer from "../../../../components/MarkdownRenderer";
import AulaChat from "../../../../components/AulaChat";
import { apiFetch, apiUrl } from "@/lib/api";

type Formula = {
  latex: string;
  nome: string;
  variaveis: string;
};

type Bloco = {
  id: number;
  paginas: string;
  resumo_markdown: string;
  formulas: Formula[];
};

type FlashcardData = {
  id: number;
  assunto: string;
  frente: string;
  verso: string;
};

type AulaDetail = {
  id: number;
  numero: number;
  titulo: string;
  status: string;
  modelo_usado: string | null;
  erro_msg: string | null;
  disciplina: { slug: string; nome: string };
  blocos: Bloco[];
  flashcards: FlashcardData[];
  total_flashcards: number;
};

type Tab = "resumo" | "formulas" | "flashcards";

export default function AulaStudyPage({
  params,
}: {
  params: Promise<{ slug: string; id: string }>;
}) {
  const { slug, id } = use(params);
  const aulaId = parseInt(id);
  const [data, setData] = useState<AulaDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<Tab>("resumo");
  const [chatOpen, setChatOpen] = useState(true);
  const [expandedCard, setExpandedCard] = useState<number | null>(null);

  useEffect(() => {
    apiFetch(`/api/aulas/${aulaId}`)
      .then((r) => r.json())
      .then((d) => setData(d))
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [aulaId]);

  if (loading) {
    return (
      <main className="w-full px-4 md:px-8 py-8">
        <div className="animate-pulse space-y-6">
          <div className="h-8 w-64 bg-surface-2 rounded" />
          <div className="h-4 w-48 bg-surface-2 rounded" />
          <div className="h-96 bg-surface-dark rounded-xl border border-border-dark" />
        </div>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="w-full px-4 md:px-8 py-8">
        <p className="text-fg-muted">Aula não encontrada.</p>
      </main>
    );
  }

  const allFormulas = data.blocos.flatMap((b) => b.formulas || []);
  const allResumo = data.blocos.map((b) => b.resumo_markdown).filter(Boolean).join("\n\n---\n\n");
  const isReady = data.status === "CONCLUIDO";

  const tabs: { key: Tab; label: string; icon: string; count?: number }[] = [
    { key: "resumo", label: "Resumo", icon: "article" },
    { key: "formulas", label: "Fórmulas", icon: "function", count: allFormulas.length },
    { key: "flashcards", label: "Flashcards", icon: "style", count: data.total_flashcards },
  ];

  return (
    <>
      {/* Header */}
      <header className="hidden md:flex sticky top-0 z-30 bg-bg-dark/80 backdrop-blur-md border-b border-border-dark px-8 py-4 justify-between items-center">
        <div className="flex items-center gap-3">
          <Link href={`/disciplinas/${slug}`} className="text-fg-muted hover:text-fg-strong transition-colors">
            <span className="material-symbols-outlined">arrow_back</span>
          </Link>
          <div>
            <p className="text-xs text-fg-faint">{data.disciplina.nome}</p>
            <h1 className="text-lg font-bold text-fg-strong">
              Aula {String(data.numero).padStart(2, "0")} — {data.titulo}
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <a
            href={apiUrl(`/api/aulas/${aulaId}/pdf`)}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-2 px-3 py-2 bg-surface-dark border border-border-dark rounded-lg text-sm text-fg hover:text-fg-strong hover:border-primary/50 transition-colors"
          >
            <span className="material-symbols-outlined text-[18px]">download</span>
            PDF Original
          </a>
          <button
            onClick={() => setChatOpen(!chatOpen)}
            className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium transition-colors ${
              chatOpen
                ? "bg-primary/15 text-primary border border-primary/30"
                : "bg-surface-dark border border-border-dark text-fg hover:text-fg-strong"
            }`}
          >
            <span className="material-symbols-outlined text-[18px]">forum</span>
            Chat
          </button>
        </div>
      </header>

      {/* Content */}
      <div className="flex h-[calc(100vh-65px)]">
        {/* Main content */}
        <main className={`flex-1 overflow-y-auto px-4 md:px-8 py-6 ${chatOpen ? "md:pr-0" : ""}`}>
          {/* Tabs */}
          <div className="flex items-center gap-1 mb-6 bg-surface-dark rounded-lg p-1 border border-border-dark w-fit">
            {tabs.map((t) => (
              <button
                key={t.key}
                onClick={() => setTab(t.key)}
                className={`flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                  tab === t.key
                    ? "bg-primary/15 text-primary"
                    : "text-fg-muted hover:text-fg-strong hover:bg-surface-2"
                }`}
              >
                <span className="material-symbols-outlined text-[18px]">{t.icon}</span>
                {t.label}
                {t.count !== undefined && t.count > 0 && (
                  <span className="px-1.5 py-0.5 bg-surface-2 text-fg-muted text-[10px] font-bold rounded-full">
                    {t.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {!isReady && (
            <div className="bg-warning/10 border border-warning/30 rounded-xl p-4 mb-6 flex items-center gap-3">
              <div className="h-4 w-4 border-2 border-warning/30 border-t-warning rounded-full animate-spin flex-shrink-0" />
              <p className="text-sm text-warning">
                O PDF ainda está sendo processado pela IA. O conteúdo aparecerá aqui quando concluído.
              </p>
            </div>
          )}

          {/* Tab: Resumo */}
          {tab === "resumo" && (
            <div className="max-w-4xl">
              {allResumo ? (
                <div className="bg-surface-dark border border-border-dark rounded-xl p-6 md:p-8">
                  <MarkdownRenderer content={allResumo} />
                </div>
              ) : (
                <div className="bg-surface-dark border border-border-dark rounded-xl p-12 text-center">
                  <span className="material-symbols-outlined text-5xl text-fg-faint mb-3 block">article</span>
                  <p className="text-fg-faint">Nenhum resumo disponível ainda.</p>
                </div>
              )}
            </div>
          )}

          {/* Tab: Fórmulas */}
          {tab === "formulas" && (
            <div className="max-w-4xl">
              {allFormulas.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {allFormulas.map((f, i) => (
                    <div
                      key={i}
                      className="bg-surface-dark border border-border-dark rounded-xl p-5 hover:border-primary/30 transition-colors"
                    >
                      <h4 className="text-sm font-semibold text-primary mb-3">{f.nome}</h4>
                      <div className="bg-bg-dark rounded-lg p-4 mb-3 text-center">
                        <MarkdownRenderer content={f.latex} />
                      </div>
                      <p className="text-xs text-fg-muted">
                        <span className="text-fg-faint font-medium">Variáveis: </span>
                        {f.variaveis}
                      </p>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="bg-surface-dark border border-border-dark rounded-xl p-12 text-center">
                  <span className="material-symbols-outlined text-5xl text-fg-faint mb-3 block">function</span>
                  <p className="text-fg-faint">Nenhuma fórmula extraída ainda.</p>
                </div>
              )}
            </div>
          )}

          {/* Tab: Flashcards */}
          {tab === "flashcards" && (
            <div className="max-w-4xl">
              {data.flashcards.length > 0 ? (
                <div className="space-y-3">
                  <div className="flex items-center justify-between mb-4">
                    <p className="text-sm text-fg-muted">
                      {data.flashcards.length} cards gerados pela IA
                    </p>
                    <Link
                      href={`/flashcards/${data.disciplina.slug}`}
                      className="flex items-center gap-2 px-4 py-2 bg-primary hover:bg-cyan-600 text-white rounded-lg text-sm font-medium transition-colors"
                    >
                      <span className="material-symbols-outlined text-[18px]">play_arrow</span>
                      Revisar Cards
                    </Link>
                  </div>

                  {data.flashcards.map((card) => (
                    <div
                      key={card.id}
                      className="bg-surface-dark border border-border-dark rounded-xl overflow-hidden hover:border-primary/30 transition-colors"
                    >
                      <button
                        onClick={() => setExpandedCard(expandedCard === card.id ? null : card.id)}
                        className="w-full flex items-center justify-between px-5 py-4 text-left"
                      >
                        <div className="flex items-center gap-3 min-w-0">
                          <span className="material-symbols-outlined text-primary text-[20px] flex-shrink-0">quiz</span>
                          <div className="min-w-0">
                            <p className="text-sm font-medium text-fg-strong truncate">{card.frente}</p>
                            <span className="text-xs text-fg-faint">{card.assunto}</span>
                          </div>
                        </div>
                        <span className={`material-symbols-outlined text-fg-faint transition-transform flex-shrink-0 ${
                          expandedCard === card.id ? "rotate-180" : ""
                        }`}>
                          expand_more
                        </span>
                      </button>
                      {expandedCard === card.id && (
                        <div className="px-5 pb-4 border-t border-border-dark pt-4">
                          <MarkdownRenderer content={card.verso} />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <div className="bg-surface-dark border border-border-dark rounded-xl p-12 text-center">
                  <span className="material-symbols-outlined text-5xl text-fg-faint mb-3 block">style</span>
                  <p className="text-fg-faint">Nenhum flashcard gerado ainda.</p>
                </div>
              )}
            </div>
          )}
        </main>

        {/* Chat sidebar */}
        {chatOpen && (
          <aside className="hidden md:flex w-[380px] flex-shrink-0 border-l border-border-dark p-4">
            <AulaChat aulaId={aulaId} disabled={!isReady} />
          </aside>
        )}
      </div>
    </>
  );
}

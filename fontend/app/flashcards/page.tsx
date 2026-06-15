"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Input } from "../components/ds";
import { apiFetch, apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

// Cores por índice para dar variedade visual aos decks
const DECK_COLORS = [
  { icon: "school", iconBg: "bg-cyan-500/10", iconColor: "text-cyan-500", ringColor: "text-cyan-500", btnStyle: "bg-primary hover:bg-cyan-600" },
  { icon: "architecture", iconBg: "bg-orange-500/10", iconColor: "text-orange-500", ringColor: "text-orange-500", btnStyle: "bg-orange-600 hover:bg-orange-700" },
  { icon: "functions", iconBg: "bg-blue-500/10", iconColor: "text-blue-500", ringColor: "text-blue-500", btnStyle: "bg-blue-600 hover:bg-blue-700" },
  { icon: "science", iconBg: "bg-purple-500/10", iconColor: "text-purple-500", ringColor: "text-purple-500", btnStyle: "bg-purple-600 hover:bg-purple-700" },
  { icon: "bolt", iconBg: "bg-green-500/10", iconColor: "text-green-500", ringColor: "text-green-500", btnStyle: "bg-green-600 hover:bg-green-700" },
  { icon: "whatshot", iconBg: "bg-red-500/10", iconColor: "text-red-500", ringColor: "text-red-500", btnStyle: "bg-red-600 hover:bg-red-700" },
];

type DeckData = {
  id: string;
  nome: string;
  icon?: string;
  icon_color?: string;
  total: number;
  revisar: number;
  pct: number;
};

export default function FlashcardsPage() {
  const queryClient = useQueryClient();

  const { data: decks = [], isPending } = useQuery({
    queryKey: qk.decks(),
    queryFn: () => apiJson<DeckData[]>("/api/decks"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) =>
      apiFetch(`/api/decks/${id}`, { method: "DELETE" }).then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.decks() });
    },
    onError: (err: Error) => {
      console.error(err);
    },
  });

  // Calcula totais para o card "Todos"
  const totalCards = decks.reduce((sum, d) => sum + d.total, 0);
  const totalRevisar = decks.reduce((sum, d) => sum + d.revisar, 0);

  return (
    <>
      <header className="hidden md:flex sticky top-0 z-30 bg-bg-dark/80 backdrop-blur-md border-b border-border-dark px-8 py-4 justify-between items-center">
        <h1 className="text-2xl font-bold text-fg-strong flex items-center gap-2">
          <span className="material-symbols-outlined text-primary">style</span>
          Biblioteca de Flashcards
        </h1>
        <div className="flex items-center gap-4">
          <button className="p-2 rounded-full hover:bg-surface-2 text-fg relative">
            <span className="material-symbols-outlined">notifications</span>
            <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-secondary animate-pulse" />
          </button>
        </div>
      </header>

      <main className="w-full px-4 md:px-8 py-8 overflow-y-auto h-full">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
          <div className="flex flex-col gap-1">
            <h2 className="text-3xl font-bold text-fg-strong">Meus Baralhos</h2>
            <p className="text-sm text-fg-muted">Gerencie seus estudos e acompanhe seu progresso diário.</p>
          </div>
          <div className="flex flex-col sm:flex-row gap-3 w-full md:w-auto">
            <div className="grow sm:grow-0 sm:w-64">
              <Input icon="search" placeholder="Buscar baralho..." />
            </div>
            <button className="p-2.5 bg-surface-dark border border-border-dark rounded-lg hover:bg-surface-2 text-fg transition-colors">
              <span className="material-symbols-outlined text-[20px]">filter_list</span>
            </button>
            <Link href="/flashcards/novo" className="flex items-center justify-center gap-2 px-5 py-2.5 bg-primary hover:bg-cyan-600 text-white rounded-lg shadow-lg shadow-cyan-500/20 transition-all font-medium whitespace-nowrap">
              <span className="material-symbols-outlined text-sm">add</span>
              Criar Novo Baralho
            </Link>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 pb-8">
          {isPending
            ? Array.from({ length: 3 }).map((_, i) => <DeckSkeleton key={i} />)
            : (
              <>
                {/* Card "Todos" - sempre primeiro */}
                {decks.length > 0 && (
                  <AllDeckCard total={totalCards} revisar={totalRevisar} />
                )}

                {decks.map((deck, idx) => (
                  <DeckCard
                    key={deck.id}
                    deck={deck}
                    colorIdx={idx}
                    onDelete={(id) => {
                      if (!confirm(`Excluir "${deck.nome}" e todos os seus cartões?`)) return;
                      deleteMutation.mutate(id);
                    }}
                  />
                ))}
              </>
            )}

          <Link href="/flashcards/novo" className="bg-surface-dark rounded-xl border border-dashed border-border hover:border-primary transition-all group flex flex-col h-full items-center justify-center cursor-pointer min-h-[300px]">
            <div className="h-16 w-16 rounded-full bg-surface-2 flex items-center justify-center mb-4 group-hover:bg-primary/10 transition-colors">
              <span className="material-symbols-outlined text-3xl text-fg-muted group-hover:text-primary">add</span>
            </div>
            <h3 className="text-lg font-bold text-fg-strong mb-2">Novo Baralho</h3>
            <p className="text-sm text-fg-muted text-center px-6">
              Adicione uma nova disciplina ou tópico para começar a criar flashcards.
            </p>
          </Link>
        </div>
      </main>
    </>
  );
}

function DeckSkeleton() {
  return (
    <div className="bg-surface-dark rounded-xl border border-border-dark p-6 animate-pulse min-h-[300px]">
      <div className="h-10 w-10 rounded-lg bg-surface-2 mb-4" />
      <div className="h-5 w-32 bg-surface-2 rounded mb-2" />
      <div className="h-3 w-24 bg-surface-2 rounded mb-6" />
      <div className="h-4 w-16 bg-surface-2 rounded mb-2" />
      <div className="h-6 w-12 bg-surface-2 rounded" />
    </div>
  );
}

function AllDeckCard({ total, revisar }: { total: number; revisar: number }) {
  return (
    <div className="bg-surface-dark rounded-xl border border-primary/30 shadow-sm hover:shadow-md hover:shadow-primary/10 hover:border-primary/60 transition-all group flex flex-col h-full">
      <div className="p-6 grow">
        <div className="flex justify-between items-start mb-4">
          <div className="h-10 w-10 rounded-lg bg-primary/15 flex items-center justify-center text-primary">
            <span className="material-symbols-outlined">library_books</span>
          </div>
        </div>
        <Link href="/flashcards/todos" className="text-lg font-bold text-fg-strong mb-1 hover:text-primary transition-colors block">Todos</Link>
        <p className="text-xs text-fg-muted mb-6">{total} cartões de todos os baralhos</p>

        <div className="flex items-center justify-between mb-6">
          <div className="space-y-3">
            <div>
              <p className="text-xs text-fg-muted uppercase font-semibold">Total de Cartões</p>
              <p className="text-xl font-bold text-fg-strong">{total}</p>
            </div>
            <div>
              <p className="text-xs text-fg-muted uppercase font-semibold">Para Revisar Hoje</p>
              <p className={`text-xl font-bold ${revisar > 0 ? "text-primary" : "text-fg-faint"}`}>
                {revisar}
              </p>
            </div>
          </div>

          <div className="relative w-16 h-16">
            <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
              <path
                className="text-border"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
              />
              <path
                className="text-primary"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none"
                stroke="currentColor"
                strokeDasharray="0, 100"
                strokeLinecap="round"
                strokeWidth="3"
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-xs font-bold text-fg-strong">0%</span>
            </div>
          </div>
        </div>
      </div>

      <div className="p-4 border-t border-border-dark bg-white/[0.02] rounded-b-xl">
        <Link
          href="/flashcards/todos"
          className="w-full py-2 bg-primary hover:bg-cyan-600 text-white rounded-lg font-medium text-sm transition-colors flex items-center justify-center gap-2"
        >
          <span className="material-symbols-outlined text-[18px]">play_arrow</span>
          Estudar Todos
        </Link>
      </div>
    </div>
  );
}

function DeckCard({ deck, colorIdx, onDelete }: { deck: DeckData; colorIdx: number; onDelete: (id: string) => void }) {
  const queryClient = useQueryClient();
  const colors = DECK_COLORS[colorIdx % DECK_COLORS.length];
  const isAllDone = deck.revisar === 0;
  const [menuOpen, setMenuOpen] = useState(false);

  function prefetchDeck() {
    queryClient.prefetchQuery({
      queryKey: qk.deckCards(deck.id),
      queryFn: () => apiJson(`/api/flashcards/${deck.id}`),
      staleTime: 30_000,
    });
  }

  return (
    <div className="relative bg-surface-dark rounded-xl border border-border-dark shadow-sm hover:shadow-md hover:border-primary/50 transition-all group flex flex-col h-full">
      {/* Corpo clicável */}
      <Link href={`/flashcards/${deck.id}`} className="p-6 grow block" onMouseEnter={prefetchDeck} onFocus={prefetchDeck}>
        <div className="flex justify-between items-start mb-4">
          <div className={`h-10 w-10 rounded-lg ${colors.iconBg} flex items-center justify-center ${colors.iconColor}`}>
            <span className="material-symbols-outlined">{colors.icon}</span>
          </div>
          {/* Menu 3 pontinhos */}
          <div className="relative">
            <button
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                setMenuOpen(!menuOpen);
              }}
              className="text-fg-muted hover:text-fg-strong p-1 rounded-lg hover:bg-surface-2 transition-colors"
            >
              <span className="material-symbols-outlined">more_vert</span>
            </button>
            {menuOpen && (
              <div
                className="absolute right-0 top-full mt-1 w-44 bg-surface-dark border border-border-dark rounded-lg shadow-xl z-50 py-1 overflow-hidden"
                onClick={(e) => { e.preventDefault(); e.stopPropagation(); }}
              >
                <button
                  onClick={() => { setMenuOpen(false); /* TODO: rename */ }}
                  className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-fg hover:bg-surface-2 hover:text-fg-strong transition-colors"
                >
                  <span className="material-symbols-outlined text-[18px]">edit</span>
                  Renomear
                </button>
                <button
                  onClick={() => { setMenuOpen(false); /* TODO: export */ }}
                  className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-fg hover:bg-surface-2 hover:text-fg-strong transition-colors"
                >
                  <span className="material-symbols-outlined text-[18px]">download</span>
                  Exportar
                </button>
                <button
                  onClick={() => { setMenuOpen(false); /* TODO: reset */ }}
                  className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-fg hover:bg-surface-2 hover:text-fg-strong transition-colors"
                >
                  <span className="material-symbols-outlined text-[18px]">restart_alt</span>
                  Resetar Progresso
                </button>
                <div className="border-t border-border-dark my-1" />
                <button
                  onClick={() => {
                    setMenuOpen(false);
                    onDelete(deck.id);
                  }}
                  className="w-full flex items-center gap-2.5 px-3.5 py-2.5 text-sm text-error hover:bg-error/15 hover:text-error transition-colors"
                >
                  <span className="material-symbols-outlined text-[18px]">delete</span>
                  Excluir Baralho
                </button>
              </div>
            )}
          </div>
        </div>
        <h3 className="text-lg font-bold text-fg-strong mb-1 group-hover:text-primary transition-colors">{deck.nome}</h3>
        <p className="text-xs text-fg-muted mb-6">{deck.total} cartões</p>

        <div className="flex items-center justify-between mb-6">
          <div className="space-y-3">
            <div>
              <p className="text-xs text-fg-muted uppercase font-semibold">Total de Cartões</p>
              <p className="text-xl font-bold text-fg-strong">{deck.total}</p>
            </div>
            <div>
              <p className="text-xs text-fg-muted uppercase font-semibold">Para Revisar Hoje</p>
              <p className={`text-xl font-bold ${deck.revisar > 0 ? "text-primary" : "text-fg-faint"}`}>
                {deck.revisar}
              </p>
            </div>
          </div>

          <div className="relative w-16 h-16">
            <svg className="w-full h-full transform -rotate-90" viewBox="0 0 36 36">
              <path
                className="text-border"
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none"
                stroke="currentColor"
                strokeWidth="3"
              />
              <path
                className={colors.ringColor}
                d="M18 2.0845 a 15.9155 15.9155 0 0 1 0 31.831 a 15.9155 15.9155 0 0 1 0 -31.831"
                fill="none"
                stroke="currentColor"
                strokeDasharray={`${deck.pct}, 100`}
                strokeLinecap="round"
                strokeWidth="3"
              />
            </svg>
            <div className="absolute inset-0 flex items-center justify-center">
              <span className="text-xs font-bold text-fg-strong">{deck.pct}%</span>
            </div>
          </div>
        </div>
      </Link>

      <div className="p-4 border-t border-border-dark bg-white/[0.02] rounded-b-xl">
        {isAllDone ? (
          <div className="w-full py-2 bg-surface-dark border border-border-strong text-fg-faint rounded-lg font-medium text-sm flex items-center justify-center gap-2">
            <span className="material-symbols-outlined text-[18px]">check</span>
            Tudo em dia
          </div>
        ) : (
          <Link
            href={`/flashcards/${deck.id}`}
            className={`w-full py-2 ${colors.btnStyle} text-white rounded-lg font-medium text-sm transition-colors flex items-center justify-center gap-2`}
          >
            <span className="material-symbols-outlined text-[18px]">play_arrow</span>
            Estudar Agora
          </Link>
        )}
      </div>

      {/* Overlay para fechar menu ao clicar fora */}
      {menuOpen && (
        <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
      )}
    </div>
  );
}

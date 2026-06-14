"use client";

import Link from "next/link";
import { use, useState, useEffect, useCallback } from "react";
import MarkdownRenderer from "../../components/MarkdownRenderer";
import { apiFetch } from "@/lib/api";

type CardData = {
  id: number;
  tema: string;
  assunto: string;
  frente: string;
  verso: string;
};

export default function FlashcardStudyPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);

  const [cards, setCards] = useState<CardData[]>([]);
  const [loading, setLoading] = useState(true);
  const [currentCard, setCurrentCard] = useState(0);
  const [isFlipped, setIsFlipped] = useState(false);
  const [timer, setTimer] = useState(0);
  const [deckName, setDeckName] = useState("");

  // Fetch cards from backend
  useEffect(() => {
    apiFetch(`/api/flashcards/${id}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.cards && data.cards.length > 0) {
          setCards(data.cards);
          setDeckName(data.deck_nome || id.replace(/-/g, " ").replace(/\b\w/g, (c: string) => c.toUpperCase()));
        }
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [id]);

  const total = cards.length;
  const card = total > 0 ? cards[currentCard % total] : null;
  const progress = total > 0 ? ((currentCard + 1) / total) * 100 : 0;

  useEffect(() => {
    const interval = setInterval(() => setTimer((t) => t + 1), 1000);
    return () => clearInterval(interval);
  }, []);

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${m.toString().padStart(2, "0")}:${sec.toString().padStart(2, "0")}`;
  };

  const handleFlip = () => {
    setIsFlipped(!isFlipped);
  };

  const goToCard = useCallback((index: number) => {
    setIsFlipped(false);
    setTimeout(() => setCurrentCard(index), 200);
  }, []);

  const handlePrev = useCallback(() => {
    if (total === 0) return;
    goToCard(currentCard > 0 ? currentCard - 1 : total - 1);
  }, [currentCard, total, goToCard]);

  const handleNext = useCallback(() => {
    if (total === 0) return;
    goToCard(currentCard < total - 1 ? currentCard + 1 : 0);
  }, [currentCard, total, goToCard]);

  const handleRandom = useCallback(() => {
    if (total <= 1) return;
    let next: number;
    do {
      next = Math.floor(Math.random() * total);
    } while (next === currentCard);
    goToCard(next);
  }, [currentCard, total, goToCard]);

  const handleRate = (level: string) => {
    // TODO: send to backend for spaced repetition
    console.log("Rated:", level);
    setIsFlipped(false);
    setTimeout(() => {
      setCurrentCard((c) => (c + 1) % Math.max(total, 1));
    }, 300);
  };

  if (loading) {
    return (
      <main className="w-full flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <div className="w-12 h-12 border-2 border-primary border-t-transparent rounded-full animate-spin" />
          <p className="text-fg-muted text-sm">Carregando cartões...</p>
        </div>
      </main>
    );
  }

  if (!card) {
    return (
      <main className="w-full flex-1 flex items-center justify-center">
        <div className="flex flex-col items-center gap-4 text-center">
          <span className="material-symbols-outlined text-5xl text-fg-faint">inbox</span>
          <p className="text-fg-muted">Nenhum cartão encontrado neste baralho.</p>
          <Link href="/flashcards" className="text-primary hover:underline text-sm">
            Voltar para a biblioteca
          </Link>
        </div>
      </main>
    );
  }

  return (
    <>
      {/* Header */}
      <header className="hidden md:flex sticky top-0 z-30 bg-bg-dark/80 backdrop-blur-md border-b border-border-dark px-8 py-4 justify-between items-center">
        <div className="flex items-center gap-4">
          <Link
            href="/flashcards"
            className="flex items-center gap-2 text-fg-faint hover:text-fg-strong transition-colors text-sm"
          >
            <span className="material-symbols-outlined text-[18px]">arrow_back</span>
            Voltar
          </Link>
          <div className="h-6 w-px bg-border" />
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-primary/15 flex items-center justify-center">
              <span className="material-symbols-outlined text-[16px] text-primary">style</span>
            </div>
            <span className="font-semibold text-fg-strong">{deckName}</span>
          </div>
        </div>
        <div className="flex items-center gap-6">
          <div className="w-28 h-[3px] bg-border rounded-full overflow-hidden">
            <div
              className="h-full bg-primary rounded-full transition-all duration-400"
              style={{ width: `${progress}%` }}
            />
          </div>
          <span className="text-sm text-fg-muted">
            Cartão <span className="text-primary font-bold">{currentCard + 1}</span> de <span className="text-primary font-bold">{total}</span>
          </span>
          <div className="flex items-center gap-2 text-sm text-fg-muted">
            <span className="material-symbols-outlined text-[16px]">timer</span>
            {formatTime(timer)}
          </div>
        </div>
      </header>

      {/* Mobile header */}
      <div className="md:hidden px-4 py-3 border-b border-border-dark flex items-center justify-between">
        <Link href="/flashcards" className="text-fg-muted hover:text-fg-strong">
          <span className="material-symbols-outlined">arrow_back</span>
        </Link>
        <span className="text-sm font-medium text-fg-strong">{deckName}</span>
        <span className="text-xs text-primary font-bold">
          {currentCard + 1}/{total}
        </span>
      </div>

      {/* Main */}
      <main className="w-full flex-1 flex flex-col items-center justify-center p-4 md:p-8 overflow-hidden relative">
        {/* Ambient glow */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
          <div className="absolute top-[20%] left-1/2 -translate-x-1/2 w-[600px] h-[400px] bg-gradient-radial from-primary/8 via-secondary/5 to-transparent rounded-full blur-3xl" />
        </div>

        <div className="relative w-full max-w-2xl flex flex-col items-center z-10">
          {/* Card area with navigation arrows */}
          <div className="w-full flex items-center gap-3 mb-8">
            {/* Left arrow */}
            <button
              onClick={handlePrev}
              className="shrink-0 w-10 h-10 rounded-full bg-surface-dark border border-border-dark flex items-center justify-center text-fg-muted hover:text-fg-strong hover:border-primary/50 transition-all"
              title="Cartão anterior"
            >
              <span className="material-symbols-outlined text-xl">chevron_left</span>
            </button>

            {/* Flashcard - click to flip */}
            <div
              className="flex-1 cursor-pointer"
              style={{ perspective: "1200px", height: "450px" }}
              onClick={handleFlip}
            >
              <div
                className="relative w-full h-full transition-transform duration-700"
                style={{
                  transformStyle: "preserve-3d",
                  transform: isFlipped ? "rotateY(180deg)" : "rotateY(0deg)",
                  transitionTimingFunction: "cubic-bezier(0.4, 0.0, 0.2, 1)",
                }}
              >
                {/* Front */}
                <div
                  className="absolute inset-0 w-full h-full bg-surface-dark border border-border-dark rounded-2xl shadow-[0_8px_32px_rgba(0,0,0,0.4),0_0_60px_rgba(6,182,212,0.04)] p-8 flex flex-col items-center justify-center"
                  style={{ backfaceVisibility: "hidden" }}
                >
                  {/* Badge top-left */}
                  <span className="absolute top-5 left-5 text-[0.7rem] font-semibold tracking-wider uppercase text-primary bg-primary/10 px-3.5 py-1 rounded-full">
                    {card.tema}
                  </span>
                  {/* Card number top-right */}
                  <span className="absolute top-5 right-5 text-xs text-fg-faint font-medium">
                    #{card.id}
                  </span>

                  {/* Assunto tag */}
                  <span className="absolute top-14 left-5 px-2.5 py-0.5 text-[0.65rem] font-medium rounded-full border bg-secondary/10 text-secondary border-secondary/20">
                    {card.assunto}
                  </span>

                  {/* Question content with markdown + LaTeX */}
                  <div className="w-full max-w-lg text-center mt-6">
                    <MarkdownRenderer
                      content={card.frente}
                      className="text-xl md:text-2xl font-medium text-fg-strong leading-relaxed [&_p]:text-xl [&_p]:md:text-2xl [&_p]:text-fg-strong [&_p]:font-medium [&_p]:leading-relaxed"
                    />
                  </div>

                  {/* Tap hint */}
                  <div className="absolute bottom-5 right-5 flex items-center gap-2 text-fg-faint text-xs animate-pulse">
                    <span className="material-symbols-outlined text-[16px]">touch_app</span>
                    Toque para ver a resposta
                  </div>
                </div>

                {/* Back */}
                <div
                  className="absolute inset-0 w-full h-full bg-surface-dark border border-border-dark rounded-2xl shadow-[0_8px_32px_rgba(0,0,0,0.4)] p-8 flex flex-col overflow-y-auto"
                  style={{
                    backfaceVisibility: "hidden",
                    transform: "rotateY(180deg)",
                  }}
                >
                  <div className="text-[0.7rem] font-semibold tracking-wider uppercase text-primary mb-4">
                    Resposta
                  </div>
                  <MarkdownRenderer content={card.verso} />
                </div>
              </div>
            </div>

            {/* Right arrow */}
            <button
              onClick={handleNext}
              className="shrink-0 w-10 h-10 rounded-full bg-surface-dark border border-border-dark flex items-center justify-center text-fg-muted hover:text-fg-strong hover:border-primary/50 transition-all"
              title="Próximo cartão"
            >
              <span className="material-symbols-outlined text-xl">chevron_right</span>
            </button>
          </div>

          {/* Random button */}
          <button
            onClick={handleRandom}
            disabled={total <= 1}
            className="mb-6 flex items-center gap-2 px-5 py-2 rounded-lg bg-surface-dark border border-border-dark text-fg-muted hover:text-primary hover:border-primary/50 transition-all text-sm font-medium disabled:opacity-30 disabled:pointer-events-none"
          >
            <span className="material-symbols-outlined text-[18px]">shuffle</span>
            Aleatório
          </button>

          {/* Rating buttons - appear when flipped */}
          <div
            className={`w-full transition-all duration-400 ${
              isFlipped
                ? "opacity-100 translate-y-0"
                : "opacity-0 translate-y-3 pointer-events-none"
            }`}
          >
            <p className="text-center text-[0.75rem] font-semibold tracking-wide uppercase text-fg-faint mb-3">
              Como foi?
            </p>
            <div className="grid grid-cols-4 gap-3">
              {[
                { key: "errei", icon: "close", label: "Errei", time: "< 1 min", color: "border-error", hoverBg: "hover:bg-red-500", text: "text-error", shadow: "hover:shadow-red-500/30" },
                { key: "dificil", icon: "bolt", label: "Difícil", time: "~3 min", color: "border-warning", hoverBg: "hover:bg-orange-500", text: "text-warning", shadow: "hover:shadow-orange-500/30" },
                { key: "bom", icon: "check", label: "Bom", time: "~7 min", color: "border-success", hoverBg: "hover:bg-green-500", text: "text-success", shadow: "hover:shadow-green-500/30" },
                { key: "facil", icon: "kid_star", label: "Fácil", time: "~15 min", color: "border-primary", hoverBg: "hover:bg-blue-500", text: "text-primary", shadow: "hover:shadow-blue-500/30" },
              ].map((btn) => (
                <button
                  key={btn.key}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleRate(btn.key);
                  }}
                  className={`flex flex-col items-center gap-1 py-3.5 px-2 rounded-xl bg-surface-dark border-2 ${btn.color} ${btn.text} ${btn.hoverBg} ${btn.shadow} hover:text-white hover:shadow-lg transition-all duration-250 group`}
                >
                  <span className="material-symbols-outlined text-xl">{btn.icon}</span>
                  <span className="font-bold text-sm">{btn.label}</span>
                  <span className="text-[0.65rem] font-medium text-fg-faint group-hover:text-white/70">
                    {btn.time}
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Footer actions */}
          <div className="flex items-center gap-4 text-sm text-fg-faint mt-6">
            <button className="hover:text-fg-strong flex items-center gap-1 transition-colors">
              <span className="material-symbols-outlined text-[18px]">edit</span> Editar Cartão
            </button>
            <span>•</span>
            <button className="hover:text-fg-strong flex items-center gap-1 transition-colors">
              <span className="material-symbols-outlined text-[18px]">flag</span> Reportar Erro
            </button>
          </div>
        </div>
      </main>
    </>
  );
}

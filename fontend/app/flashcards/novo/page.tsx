"use client";

import Link from "next/link";
import { useState, useRef } from "react";
import MarkdownRenderer from "../../components/MarkdownRenderer";

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type ParsedCard = {
  id: number;
  tema: string;
  assunto: string;
  frente: string;
  verso: string;
};

type Tab = "individual" | "importar";

export default function NovoFlashcardPage() {
  const [tab, setTab] = useState<Tab>("importar");

  return (
    <>
      {/* Header */}
      <header className="hidden md:flex sticky top-0 z-30 bg-page/80 backdrop-blur-md border-b border-border px-8 py-4 justify-between items-center">
        <div className="flex items-center gap-4">
          <Link
            href="/flashcards"
            className="flex items-center gap-2 text-fg-faint hover:text-fg-strong transition-colors text-sm"
          >
            <span className="material-symbols-outlined text-[18px]">arrow_back</span>
            Voltar
          </Link>
          <div className="h-6 w-px bg-border" />
          <h1 className="text-xl font-bold text-fg-strong flex items-center gap-2">
            <span className="material-symbols-outlined text-primary">add_circle</span>
            Novo Flashcard
          </h1>
        </div>
      </header>

      <main className="w-full px-4 md:px-8 py-8 overflow-y-auto h-full">
        {/* Tabs */}
        <div className="flex gap-1 mb-8 bg-surface rounded-xl p-1 w-fit">
          <button
            onClick={() => setTab("individual")}
            className={`px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
              tab === "individual"
                ? "bg-primary text-white shadow-lg shadow-cyan-500/20"
                : "text-fg-muted hover:text-fg-strong"
            }`}
          >
            <span className="material-symbols-outlined text-[16px] mr-1 align-middle">edit_note</span>
            Criar Individual
          </button>
          <button
            onClick={() => setTab("importar")}
            className={`px-5 py-2.5 rounded-lg text-sm font-medium transition-all ${
              tab === "importar"
                ? "bg-primary text-white shadow-lg shadow-cyan-500/20"
                : "text-fg-muted hover:text-fg-strong"
            }`}
          >
            <span className="material-symbols-outlined text-[16px] mr-1 align-middle">upload_file</span>
            Importar Lista
          </button>
        </div>

        {tab === "individual" ? <IndividualForm /> : <ImportForm />}
      </main>
    </>
  );
}

// ─── Criar Individual ────────────────────────────────────

function IndividualForm() {
  const [tema, setTema] = useState("");
  const [assunto, setAssunto] = useState("");
  const [frente, setFrente] = useState("");
  const [verso, setVerso] = useState("");
  const [showPreview, setShowPreview] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const handleSave = async () => {
    if (!tema || !frente || !verso) return;
    setSaving(true);
    try {
      await fetch(`${API_URL}/api/flashcards`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ tema, assunto: assunto || tema, frente, verso }),
      });
      setSaved(true);
      setTimeout(() => {
        setSaved(false);
        setFrente("");
        setVerso("");
        setAssunto("");
      }, 2000);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="max-w-4xl">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div>
          <label className="block text-xs font-semibold text-fg-muted uppercase tracking-wider mb-2">
            Tema / Disciplina
          </label>
          <input
            value={tema}
            onChange={(e) => setTema(e.target.value)}
            className="w-full px-4 py-2.5 bg-surface border border-border rounded-lg text-sm text-fg-strong placeholder:text-fg-faint focus:ring-primary focus:border-primary"
            placeholder="ex: Geotecnia"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-fg-muted uppercase tracking-wider mb-2">
            Assunto
          </label>
          <input
            value={assunto}
            onChange={(e) => setAssunto(e.target.value)}
            className="w-full px-4 py-2.5 bg-surface border border-border rounded-lg text-sm text-fg-strong placeholder:text-fg-faint focus:ring-primary focus:border-primary"
            placeholder="ex: Bulbo de Tensões"
          />
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div>
          <label className="block text-xs font-semibold text-fg-muted uppercase tracking-wider mb-2">
            Frente (Pergunta)
          </label>
          <textarea
            value={frente}
            onChange={(e) => setFrente(e.target.value)}
            rows={6}
            className="w-full px-4 py-3 bg-surface border border-border rounded-lg text-sm text-fg-strong placeholder:text-fg-faint focus:ring-primary focus:border-primary resize-none font-mono"
            placeholder="Suporta **markdown**, $LaTeX$ e tags XML..."
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-fg-muted uppercase tracking-wider mb-2">
            Verso (Resposta)
          </label>
          <textarea
            value={verso}
            onChange={(e) => setVerso(e.target.value)}
            rows={6}
            className="w-full px-4 py-3 bg-surface border border-border rounded-lg text-sm text-fg-strong placeholder:text-fg-faint focus:ring-primary focus:border-primary resize-none font-mono"
            placeholder="Use <atencao>, <destaque>, <resumo>..."
          />
        </div>
      </div>

      {/* Preview toggle */}
      <button
        onClick={() => setShowPreview(!showPreview)}
        className="flex items-center gap-2 text-sm text-fg-muted hover:text-primary mb-4 transition-colors"
      >
        <span className="material-symbols-outlined text-[18px]">
          {showPreview ? "visibility_off" : "visibility"}
        </span>
        {showPreview ? "Esconder Preview" : "Ver Preview"}
      </button>

      {showPreview && (frente || verso) && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          <div className="bg-surface border border-border rounded-xl p-6">
            <p className="text-[0.7rem] font-semibold tracking-wider uppercase text-primary mb-3">
              Frente
            </p>
            <MarkdownRenderer content={frente} />
          </div>
          <div className="bg-surface border border-border rounded-xl p-6">
            <p className="text-[0.7rem] font-semibold tracking-wider uppercase text-primary mb-3">
              Verso
            </p>
            <MarkdownRenderer content={verso} />
          </div>
        </div>
      )}

      <button
        onClick={handleSave}
        disabled={!tema || !frente || !verso || saving}
        className="flex items-center justify-center gap-2 px-8 py-3 bg-primary hover:bg-cyan-600 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg shadow-lg shadow-cyan-500/20 transition-all font-medium"
      >
        {saved ? (
          <>
            <span className="material-symbols-outlined text-[18px]">check</span>
            Salvo!
          </>
        ) : saving ? (
          "Salvando..."
        ) : (
          <>
            <span className="material-symbols-outlined text-[18px]">save</span>
            Criar Flashcard
          </>
        )}
      </button>
    </div>
  );
}

// ─── Importar Lista ──────────────────────────────────────

function ImportForm() {
  const [text, setText] = useState("");
  const [cards, setCards] = useState<ParsedCard[]>([]);
  const [previewIdx, setPreviewIdx] = useState<number | null>(null);
  const [importing, setImporting] = useState(false);
  const [imported, setImported] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    const content = await file.text();
    setText(content);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file && file.name.endsWith(".md")) {
      handleFile(file);
    }
  };

  const handleParse = async () => {
    if (!text.trim()) return;
    setImporting(true);
    setError(null);
    try {
      const blob = new Blob([text], { type: "text/markdown" });
      const formData = new FormData();
      formData.append("file", blob, "flashcards.md");

      const res = await fetch(`${API_URL}/api/flashcards/import`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        throw new Error(`Erro ${res.status}: ${res.statusText}`);
      }
      const data = await res.json();
      setCards(data.cards || []);
      setImported(true);
    } catch (err) {
      console.error("Erro ao importar:", err);
      setError(err instanceof Error ? err.message : "Erro ao conectar com o servidor");
    } finally {
      setImporting(false);
    }
  };

  const handleReset = () => {
    setText("");
    setCards([]);
    setImported(false);
    setPreviewIdx(null);
  };

  return (
    <div className="max-w-5xl">
      {!imported ? (
        <>
          {/* Drop zone */}
          <div
            onDragOver={(e) => e.preventDefault()}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className="border-2 border-dashed border-border hover:border-primary rounded-xl p-8 text-center cursor-pointer transition-colors mb-6 group"
          >
            <span className="material-symbols-outlined text-4xl text-fg-faint group-hover:text-primary mb-2 block">
              upload_file
            </span>
            <p className="text-fg-muted text-sm">
              Arraste um arquivo <strong className="text-fg-strong">.md</strong> aqui ou clique para selecionar
            </p>
            <input
              ref={fileInputRef}
              type="file"
              accept=".md"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFile(file);
              }}
            />
          </div>

          {/* Textarea */}
          <div className="mb-6">
            <label className="block text-xs font-semibold text-fg-muted uppercase tracking-wider mb-2">
              Ou cole o conteúdo aqui
            </label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={16}
              className="w-full px-4 py-3 bg-surface border border-border rounded-lg text-sm text-fg-strong placeholder:text-fg-faint focus:ring-primary focus:border-primary resize-none font-mono leading-relaxed"
              placeholder={`Flashcard: Tema: Assunto\nFrente: Pergunta aqui...\nVerso:\nResposta com **markdown**, $LaTeX$ e <atencao>tags</atencao>...\n\nFlashcard: Tema: Outro Assunto\n...`}
            />
          </div>

          {error && (
            <div className="mb-4 bg-red-500/10 border border-red-500/30 rounded-lg p-3 flex items-center gap-2 text-red-400 text-sm">
              <span className="material-symbols-outlined text-[18px]">error</span>
              {error}
            </div>
          )}

          <button
            onClick={handleParse}
            disabled={!text.trim() || importing}
            className="flex items-center justify-center gap-2 px-8 py-3 bg-primary hover:bg-cyan-600 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded-lg shadow-lg shadow-cyan-500/20 transition-all font-medium"
          >
            {importing ? (
              "Processando..."
            ) : (
              <>
                <span className="material-symbols-outlined text-[18px]">auto_awesome</span>
                Importar Flashcards
              </>
            )}
          </button>
        </>
      ) : (
        <>
          {/* Success banner */}
          <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-4 mb-6 flex items-center gap-3">
            <span className="material-symbols-outlined text-green-400 text-2xl">check_circle</span>
            <div>
              <p className="text-fg-strong font-bold">
                {cards.length} flashcards importados!
              </p>
              <p className="text-sm text-fg-muted">
                Temas: {[...new Set(cards.map((c) => c.tema))].join(", ")}
              </p>
            </div>
            <button
              onClick={handleReset}
              className="ml-auto px-4 py-2 text-sm bg-surface border border-border rounded-lg text-fg hover:text-fg-strong transition-colors"
            >
              Importar mais
            </button>
          </div>

          {/* Cards list */}
          <div className="space-y-3">
            {cards.map((card, idx) => (
              <div
                key={card.id}
                className="bg-surface border border-border rounded-xl overflow-hidden"
              >
                <button
                  onClick={() => setPreviewIdx(previewIdx === idx ? null : idx)}
                  className="w-full px-5 py-4 flex items-center gap-4 text-left hover:bg-white/2 transition-colors"
                >
                  <span className="text-xs font-mono text-fg-faint w-8">#{card.id}</span>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <span className="text-[0.65rem] font-semibold uppercase tracking-wider text-primary bg-primary/10 px-2 py-0.5 rounded-full">
                        {card.tema}
                      </span>
                      <span className="text-[0.65rem] text-fg-faint">{card.assunto}</span>
                    </div>
                    <p className="text-sm text-fg truncate">{card.frente}</p>
                  </div>
                  <span className="material-symbols-outlined text-fg-faint text-[18px]">
                    {previewIdx === idx ? "expand_less" : "expand_more"}
                  </span>
                </button>

                {previewIdx === idx && (
                  <div className="px-5 pb-5 border-t border-border">
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4">
                      <div className="bg-inset rounded-lg p-4">
                        <p className="text-[0.65rem] font-semibold uppercase tracking-wider text-cyan-400 mb-2">
                          Frente
                        </p>
                        <MarkdownRenderer content={card.frente} />
                      </div>
                      <div className="bg-inset rounded-lg p-4">
                        <p className="text-[0.65rem] font-semibold uppercase tracking-wider text-cyan-400 mb-2">
                          Verso
                        </p>
                        <MarkdownRenderer content={card.verso} />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}

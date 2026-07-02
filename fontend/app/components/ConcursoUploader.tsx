"use client";

import { useState, useRef } from "react";

type Props = {
  onUpload: (file: File, nome: string, publico: boolean) => Promise<void>;
  uploading?: boolean;
  /** Admin pode publicar o import no catálogo visível a todos. */
  isAdmin?: boolean;
};

export default function ConcursoUploader({ onUpload, uploading = false, isAdmin = false }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [nome, setNome] = useState("");
  const [publico, setPublico] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = (f: File | undefined | null) => {
    if (!f) return;
    setFile(f);
    if (!nome) setNome(f.name.replace(/\.csv$/i, ""));
  };

  const submit = async () => {
    if (!file || uploading) return;
    await onUpload(file, nome.trim(), isAdmin && publico);
    setFile(null);
    setNome("");
    setPublico(false);
    if (inputRef.current) inputRef.current.value = "";
  };

  return (
    <div className="space-y-4">
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={(e) => { e.preventDefault(); setDragOver(false); pick(e.dataTransfer.files[0]); }}
        onClick={() => inputRef.current?.click()}
        className={`relative overflow-hidden border border-dashed rounded-2xl p-10 text-center cursor-pointer transition-all ${
          dragOver
            ? "border-primary bg-primary/5"
            : file
            ? "border-accent-success/50 bg-accent-success/5"
            : "border-border hover:border-primary/50 bg-page/40"
        }`}
      >
        <input ref={inputRef} type="file" accept=".csv,text/csv" onChange={(e) => pick(e.target.files?.[0])} className="hidden" />
        {file ? (
          <div className="flex flex-col items-center gap-2">
            <span className="material-symbols-outlined text-5xl text-accent-success">table_view</span>
            <p className="text-sm font-medium text-fg-strong">{file.name}</p>
            <p className="text-xs text-fg-faint font-mono">{(file.size / 1024).toFixed(0)} KB</p>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setFile(null); }}
              className="text-xs text-accent-error hover:underline mt-1"
            >
              Remover
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-3">
            <span className="material-symbols-outlined text-5xl text-fg-faint">upload_file</span>
            <div>
              <p className="text-sm text-fg">Arraste o CSV de concorrência aqui</p>
              <p className="text-xs text-fg-faint mt-1">colunas: CARGO, POLO, MACROPOLO, PONTOS, AC, PCD, PN, PI, PQ…</p>
            </div>
          </div>
        )}
      </div>

      {file && (
        <div className="flex flex-col sm:flex-row gap-3">
          <input
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Nome do concurso (ex: CNU 2025 - Engenharia)"
            className="flex-1 px-4 py-2.5 bg-page border border-border rounded-lg text-sm text-fg-strong placeholder:text-fg-faint focus:ring-1 focus:ring-primary focus:border-primary"
          />
          {isAdmin && (
            <button
              type="button"
              onClick={() => setPublico((p) => !p)}
              title="Concursos do catálogo ficam visíveis para todos os usuários do studIA"
              className={`flex items-center gap-2 px-4 py-2.5 rounded-lg border text-sm font-medium transition-all ${
                publico
                  ? "border-primary bg-primary/15 text-primary ring-1 ring-primary/40"
                  : "border-border text-fg-muted hover:border-primary/50"
              }`}
            >
              <span className="material-symbols-outlined text-[18px]">{publico ? "public" : "lock"}</span>
              {publico ? "Publicar no catálogo" : "Só para mim"}
            </button>
          )}
          <button
            type="button"
            onClick={submit}
            disabled={uploading}
            className="flex items-center justify-center gap-2 px-6 py-2.5 bg-primary hover:bg-cyan-600 text-white rounded-lg shadow-lg shadow-cyan-500/20 transition-all font-medium disabled:opacity-40"
          >
            {uploading ? (
              <><div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> Processando…</>
            ) : (
              <><span className="material-symbols-outlined text-sm">analytics</span> Analisar concorrência</>
            )}
          </button>
        </div>
      )}
    </div>
  );
}

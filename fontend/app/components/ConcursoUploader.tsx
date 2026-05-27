"use client";

import { useState, useRef } from "react";

type Props = {
  onUpload: (file: File, nome: string) => Promise<void>;
  uploading?: boolean;
};

export default function ConcursoUploader({ onUpload, uploading = false }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [nome, setNome] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const pick = (f: File | undefined | null) => {
    if (!f) return;
    setFile(f);
    if (!nome) setNome(f.name.replace(/\.csv$/i, ""));
  };

  const submit = async () => {
    if (!file || uploading) return;
    await onUpload(file, nome.trim());
    setFile(null);
    setNome("");
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
            : "border-border-dark hover:border-primary/50 bg-bg-dark/40"
        }`}
      >
        <input ref={inputRef} type="file" accept=".csv,text/csv" onChange={(e) => pick(e.target.files?.[0])} className="hidden" />
        {file ? (
          <div className="flex flex-col items-center gap-2">
            <span className="material-symbols-outlined text-5xl text-accent-success">table_view</span>
            <p className="text-sm font-medium text-white">{file.name}</p>
            <p className="text-xs text-gray-500 font-mono">{(file.size / 1024).toFixed(0)} KB</p>
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
            <span className="material-symbols-outlined text-5xl text-gray-600">upload_file</span>
            <div>
              <p className="text-sm text-gray-300">Arraste o CSV de concorrência aqui</p>
              <p className="text-xs text-gray-600 mt-1">colunas: CARGO, POLO, MACROPOLO, PONTOS, AC, PCD, PN, PI, PQ…</p>
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
            className="flex-1 px-4 py-2.5 bg-bg-dark border border-border-dark rounded-lg text-sm text-white placeholder-gray-600 focus:ring-1 focus:ring-primary focus:border-primary"
          />
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

"use client";

import { useState, useRef } from "react";
import ModelSelector from "./ModelSelector";

type PdfUploaderProps = {
  onUpload: (file: File, modelo: string) => Promise<void>;
  uploading?: boolean;
};

export default function PdfUploader({ onUpload, uploading = false }: PdfUploaderProps) {
  const [file, setFile] = useState<File | null>(null);
  const [modelo, setModelo] = useState("gemini-3-flash-preview");
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped?.type === "application/pdf") {
      setFile(dropped);
    }
  };

  const handleSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const selected = e.target.files?.[0];
    if (selected) setFile(selected);
  };

  const handleSubmit = async () => {
    if (!file || uploading) return;
    await onUpload(file, modelo);
    setFile(null);
    if (inputRef.current) inputRef.current.value = "";
  };

  const fileSizeMB = file ? (file.size / (1024 * 1024)).toFixed(1) : "0";

  return (
    <div className="bg-surface-dark border border-border-dark rounded-xl p-6 space-y-5">
      <h3 className="text-sm font-semibold text-white flex items-center gap-2">
        <span className="material-symbols-outlined text-primary">upload_file</span>
        Upload de Aula (PDF)
      </h3>

      {/* Drop zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
        className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-all ${
          dragOver
            ? "border-primary bg-primary/5"
            : file
            ? "border-accent-success/50 bg-accent-success/5"
            : "border-gray-700 hover:border-primary/50"
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf"
          onChange={handleSelect}
          className="hidden"
        />
        {file ? (
          <div className="flex flex-col items-center gap-2">
            <span className="material-symbols-outlined text-4xl text-accent-success">picture_as_pdf</span>
            <p className="text-sm font-medium text-white">{file.name}</p>
            <p className="text-xs text-gray-500">{fileSizeMB} MB</p>
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); setFile(null); }}
              className="text-xs text-accent-error hover:underline mt-1"
            >
              Remover
            </button>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-2">
            <span className="material-symbols-outlined text-4xl text-gray-600">cloud_upload</span>
            <p className="text-sm text-gray-400">Arraste um PDF aqui ou clique para selecionar</p>
            <p className="text-xs text-gray-600">Máximo 50MB</p>
          </div>
        )}
      </div>

      {/* Model selector */}
      <ModelSelector value={modelo} onChange={setModelo} />

      {/* Submit */}
      <button
        type="button"
        onClick={handleSubmit}
        disabled={!file || uploading}
        className="w-full flex items-center justify-center gap-2 px-4 py-3 bg-primary hover:bg-cyan-600 text-white rounded-lg shadow-lg shadow-cyan-500/20 transition-all font-medium disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {uploading ? (
          <>
            <div className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Enviando...
          </>
        ) : (
          <>
            <span className="material-symbols-outlined text-sm">rocket_launch</span>
            Enviar e Processar com IA
          </>
        )}
      </button>
    </div>
  );
}

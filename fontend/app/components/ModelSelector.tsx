"use client";

import { useState, useRef, useEffect } from "react";

type ModelOption = {
  value: string;
  label: string;
  description: string;
  pricing: string;
  recommended?: boolean;
};

const GEMINI_MODELS: ModelOption[] = [
  { value: "gemini-3.1-pro-preview", label: "Gemini 3.1 Pro Preview", description: "SOTA reasoning com profundidade e multimodal avançado", pricing: "≤200K: $2.00 / $12.00 · >200K: $4.00 / $18.00" },
  { value: "gemini-3-flash-preview", label: "Gemini 3 Flash Preview", recommended: true, description: "Inteligência frontier com velocidade, search e grounding", pricing: "$0.50 / $3.00 por 1M tokens" },
  { value: "gemini-3-pro-preview", label: "Gemini 3 Pro Preview", description: "Raciocínio avançado, multimodal e vibe coding", pricing: "≤200K: $2.00 / $12.00 · >200K: $4.00 / $18.00" },
  { value: "gemini-2.5-pro", label: "Gemini 2.5 Pro", description: "Geração anterior, excelente em código e raciocínio complexo", pricing: "≤200K: $1.25 / $10.00 · >200K: $2.50 / $15.00" },
  { value: "gemini-2.5-flash", label: "Gemini 2.5 Flash", description: "Raciocínio híbrido, 1M context, thinking budgets", pricing: "$0.30 / $2.50 por 1M tokens" },
  { value: "gemini-2.5-flash-lite", label: "Gemini 2.5 Flash Lite", description: "Menor e mais econômico, feito para uso em escala", pricing: "$0.10 / $0.40 por 1M tokens" },
  { value: "gemini-flash-latest", label: "Gemini Flash (latest)", description: "Alias automático → gemini-2.5-flash-preview mais recente", pricing: "$0.30 / $2.50 por 1M tokens" },
  { value: "gemini-flash-lite-latest", label: "Gemini Flash Lite (latest)", description: "Alias automático → Flash Lite mais recente", pricing: "$0.10 / $0.40 por 1M tokens" },
];

type ModelSelectorProps = {
  value: string;
  onChange: (value: string) => void;
  compact?: boolean;
};

export default function ModelSelector({ value, onChange, compact = false }: ModelSelectorProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const selected = GEMINI_MODELS.find((m) => m.value === value) || GEMINI_MODELS[1];

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  if (compact) {
    return (
      <div ref={ref} className="relative">
        <button
          type="button"
          onClick={() => setOpen(!open)}
          className="flex items-center gap-1.5 px-2 py-1 bg-surface-dark border border-border-dark rounded-lg text-xs text-gray-300 hover:border-primary/50 transition-colors"
        >
          <span className="material-symbols-outlined text-primary text-[14px]">smart_toy</span>
          <span className="truncate max-w-[120px]">{selected.label}</span>
          <span className="material-symbols-outlined text-[14px]">expand_more</span>
        </button>
        {open && (
          <div className="absolute bottom-full mb-1 left-0 w-80 bg-surface-dark border border-border-dark rounded-xl shadow-2xl z-50 max-h-80 overflow-y-auto">
            {GEMINI_MODELS.map((m) => (
              <button
                key={m.value}
                type="button"
                onClick={() => { onChange(m.value); setOpen(false); }}
                className={`w-full text-left px-3 py-2.5 hover:bg-gray-800 transition-colors first:rounded-t-xl last:rounded-b-xl ${
                  m.value === value ? "bg-primary/10" : ""
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-white">{m.label}</span>
                  {m.recommended && (
                    <span className="px-1.5 py-0.5 bg-primary/20 text-primary text-[10px] font-bold rounded">REC</span>
                  )}
                </div>
                <p className="text-xs text-gray-500 mt-0.5">{m.pricing}</p>
              </button>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div ref={ref} className="relative">
      <label className="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">
        Modelo de IA
      </label>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between px-4 py-3 bg-surface-dark border border-border-dark rounded-lg text-sm text-white hover:border-primary/50 transition-colors"
      >
        <div className="flex items-center gap-3">
          <span className="material-symbols-outlined text-primary">smart_toy</span>
          <div className="text-left">
            <div className="flex items-center gap-2">
              <span className="font-medium">{selected.label}</span>
              {selected.recommended && (
                <span className="px-1.5 py-0.5 bg-primary/20 text-primary text-[10px] font-bold rounded">Recomendado</span>
              )}
            </div>
            <p className="text-xs text-gray-500">{selected.pricing}</p>
          </div>
        </div>
        <span className="material-symbols-outlined text-gray-400">expand_more</span>
      </button>
      {open && (
        <div className="absolute top-full mt-1 left-0 right-0 bg-surface-dark border border-border-dark rounded-xl shadow-2xl z-50 max-h-80 overflow-y-auto">
          {GEMINI_MODELS.map((m) => (
            <button
              key={m.value}
              type="button"
              onClick={() => { onChange(m.value); setOpen(false); }}
              className={`w-full text-left px-4 py-3 hover:bg-gray-800 transition-colors first:rounded-t-xl last:rounded-b-xl ${
                m.value === value ? "bg-primary/10 border-l-2 border-primary" : ""
              }`}
            >
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-white">{m.label}</span>
                {m.recommended && (
                  <span className="px-1.5 py-0.5 bg-primary/20 text-primary text-[10px] font-bold rounded">Recomendado</span>
                )}
              </div>
              <p className="text-xs text-gray-400 mt-0.5">{m.description}</p>
              <p className="text-xs text-gray-500 mt-0.5">{m.pricing}</p>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export { GEMINI_MODELS };
export type { ModelOption };

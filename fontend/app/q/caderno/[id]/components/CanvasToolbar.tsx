"use client";

import { Icon } from "../../../../components/ds/Icon";
import type { CanvasTool } from "../annotations/types";

export interface CanvasToolbarProps {
  active: boolean;
  tool: CanvasTool;
  color: string;
  width: number;
  hasStrokes: boolean;
  saving: boolean;
  saveError: string | null;
  onActiveChange: (active: boolean) => void;
  onToolChange: (tool: CanvasTool) => void;
  onColorChange: (color: string) => void;
  onWidthChange: (width: number) => void;
  onClear: () => void;
  onOpenCalculator: () => void;
}

const TOOLS: Array<{ id: CanvasTool; icon: string; label: string }> = [
  { id: "pen", icon: "draw", label: "Lapis" },
  { id: "highlight", icon: "ink_highlighter", label: "Marca-texto" },
  { id: "eraser", icon: "ink_eraser", label: "Borracha" },
];

export function CanvasToolbar({
  active,
  tool,
  color,
  width,
  hasStrokes,
  saving,
  saveError,
  onActiveChange,
  onToolChange,
  onColorChange,
  onWidthChange,
  onClear,
  onOpenCalculator,
}: CanvasToolbarProps) {
  return (
    <div className="relative z-30 flex flex-wrap items-center gap-2 text-xs">
      <button
        type="button"
        role="switch"
        aria-checked={active}
        onClick={() => onActiveChange(!active)}
        className={`inline-flex h-8 items-center gap-2 rounded-full border px-2.5 transition ${
          active
            ? "border-cyan-400 bg-cyan-500/15 text-cyan-100"
            : "border-gray-700 bg-gray-950/70 text-gray-400 hover:border-gray-600 hover:text-gray-100"
        }`}
        title="Ativar ou desativar canvas"
      >
        <span
          className={`flex h-4 w-7 items-center rounded-full p-0.5 transition ${
            active ? "bg-cyan-500" : "bg-gray-700"
          }`}
          aria-hidden="true"
        >
          <span className={`block h-3 w-3 rounded-full bg-white transition ${active ? "translate-x-3" : ""}`} />
        </span>
        Canvas
      </button>

      {active && (
        <>
          <div className="flex items-center gap-1 rounded-lg border border-gray-700 bg-gray-950/80 p-1">
            {TOOLS.map((item) => (
              <button
                key={item.id}
                type="button"
                aria-label={item.label}
                aria-pressed={tool === item.id}
                onClick={() => onToolChange(item.id)}
                className={`grid h-7 w-7 place-items-center rounded transition ${
                  tool === item.id
                    ? "bg-cyan-500 text-white shadow-sm shadow-cyan-500/20"
                    : "text-gray-400 hover:bg-gray-800 hover:text-white"
                }`}
                title={item.label}
              >
                <Icon name={item.icon} size={18} />
              </button>
            ))}
          </div>

          <input
            type="color"
            value={color}
            onChange={(event) => onColorChange(event.target.value)}
            className="h-8 w-8 rounded border border-gray-700 bg-gray-950 p-0.5"
            title="Cor do traco"
            aria-label="Cor do traco"
          />

          <label className="flex h-8 items-center gap-2 rounded border border-gray-700 bg-gray-950/70 px-2 text-gray-400">
            <span className="sr-only">Espessura</span>
            <span className="font-mono text-[11px] text-gray-500" aria-hidden="true">
              {width}px
            </span>
            <input
              type="range"
              min={2}
              max={18}
              value={width}
              onChange={(event) => onWidthChange(Number(event.target.value))}
              className="w-24 accent-cyan-500"
              title="Espessura"
              aria-label="Espessura"
            />
          </label>

          <button
            type="button"
            disabled={!hasStrokes}
            onClick={onClear}
            className="inline-flex h-8 items-center gap-1 rounded border border-gray-700 px-2 text-gray-300 transition hover:bg-gray-800 disabled:cursor-not-allowed disabled:opacity-40"
            title="Limpar canvas"
          >
            <Icon name="delete" size={16} />
            Limpar
          </button>
        </>
      )}

      <button
        type="button"
        onClick={onOpenCalculator}
        className="inline-flex h-8 items-center gap-1 rounded border border-gray-700 px-2 text-gray-300 transition hover:bg-gray-800"
        title="Calculadora"
      >
        <Icon name="calculate" size={16} />
        Calc
      </button>

      {(saving || saveError) && (
        <span className={`text-[11px] ${saveError ? "text-amber-300" : "text-gray-500"}`} title={saveError ?? undefined}>
          {saving ? "Salvando..." : "Erro ao salvar"}
        </span>
      )}
    </div>
  );
}

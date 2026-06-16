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
            ? "border-primary bg-primary/15 text-primary"
            : "border-border bg-page/70 text-fg-muted hover:border-border-strong hover:text-fg-strong"
        }`}
        title="Ativar ou desativar canvas"
      >
        <span
          className={`flex h-4 w-7 items-center rounded-full p-0.5 transition ${
            active ? "bg-cyan-500" : "bg-surface-2"
          }`}
          aria-hidden="true"
        >
          <span className={`block h-3 w-3 rounded-full bg-white transition ${active ? "translate-x-3" : ""}`} />
        </span>
        Canvas
      </button>

      {/* Bloco de ferramentas SEMPRE montado: quando o canvas está desligado
          fica `invisible` (some visualmente e sai da ordem de tab) mas continua
          ocupando o mesmo espaço — assim o toggle Canvas e o botão Calc não
          pulam de lugar ao ligar/desligar; ficam fixos na posição do modo ativo. */}
      <div
        className={`flex flex-wrap items-center gap-2 ${active ? "" : "invisible"}`}
        aria-hidden={active ? undefined : true}
      >
        <div className="flex items-center gap-1 rounded-lg border border-border bg-page/80 p-1">
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
                    : "text-fg-muted hover:bg-surface-2 hover:text-fg-strong"
                }`}
                title={item.label}
              >
                <Icon name={item.icon} size={18} aria-hidden="true" />
              </button>
            ))}
          </div>

          <input
            type="color"
            value={color}
            onChange={(event) => onColorChange(event.target.value)}
            className="h-8 w-8 rounded border border-border bg-page p-0.5"
            title="Cor do traco"
            aria-label="Cor do traco"
          />

          <label className="flex h-8 items-center gap-2 rounded border border-border bg-page/70 px-2 text-fg-muted">
            <span className="sr-only">Espessura</span>
            <span className="w-8 text-right font-mono text-[11px] text-fg-faint" aria-hidden="true">
              {width}px
            </span>
            <input
              type="range"
              min={2}
              max={18}
              value={width}
              onChange={(event) => onWidthChange(Number(event.target.value))}
              className="w-24 accent-primary"
              title="Espessura"
              aria-label="Espessura"
            />
          </label>

          <button
            type="button"
            disabled={!hasStrokes}
            onClick={onClear}
            className="inline-flex h-8 items-center gap-1 rounded border border-border px-2 text-fg transition hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-40"
            title="Limpar canvas"
          >
            <Icon name="delete" size={16} aria-hidden="true" />
            Limpar
          </button>
      </div>

      <button
        type="button"
        onClick={onOpenCalculator}
        className="inline-flex h-8 items-center gap-1 rounded border border-border px-2 text-fg transition hover:bg-surface-2"
        title="Calculadora"
      >
        <Icon name="calculate" size={16} aria-hidden="true" />
        Calc
      </button>

      {/* Slot de largura fixa: montar/desmontar texto aqui mudava a largura da
          toolbar a cada autosave e fazia o card inteiro reflowar. */}
      <span
        role="status"
        aria-live="polite"
        className="flex h-8 w-4 items-center justify-center"
        title={saveError ? `Erro ao salvar: ${saveError}` : saving ? "Salvando anotações" : undefined}
      >
        {saving ? (
          <span
            className="h-3 w-3 animate-spin rounded-full border-2 border-border-strong border-t-primary"
            aria-hidden="true"
          />
        ) : saveError ? (
          <Icon name="error" size={14} className="text-warning" aria-hidden="true" />
        ) : null}
        <span className="sr-only">
          {saving ? "Salvando anotações" : saveError ? "Erro ao salvar anotações" : ""}
        </span>
      </span>
    </div>
  );
}

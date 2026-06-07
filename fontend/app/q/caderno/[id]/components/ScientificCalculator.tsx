"use client";

import { useCallback, useEffect, useState } from "react";
import { Icon } from "../../../../components/ds/Icon";
import { createCalculatorHistory, fetchCalculatorHistory } from "../annotations/api";
import type { CalculatorHistoryItem } from "../annotations/types";
import { evaluateExpression } from "./math";

export interface ScientificCalculatorProps {
  open: boolean;
  cadernoId: number;
  questaoId: number;
  onClose: () => void;
}

type CalculatorKey =
  | { label: string; value: string; tone?: "number" | "operator" | "function" }
  | { label: string; action: "clear" | "backspace" | "equals"; tone?: "danger" | "operator" };

const KEYS: CalculatorKey[] = [
  { label: "C", action: "clear", tone: "danger" },
  { label: "⌫", action: "backspace" },
  { label: "(", value: "(", tone: "operator" },
  { label: ")", value: ")", tone: "operator" },
  { label: "sin", value: "sin(", tone: "function" },
  { label: "cos", value: "cos(", tone: "function" },
  { label: "tan", value: "tan(", tone: "function" },
  { label: "√", value: "sqrt(", tone: "function" },
  { label: "log", value: "log(", tone: "function" },
  { label: "ln", value: "ln(", tone: "function" },
  { label: "^", value: "^", tone: "operator" },
  { label: "%", value: "%", tone: "operator" },
  { label: "7", value: "7", tone: "number" },
  { label: "8", value: "8", tone: "number" },
  { label: "9", value: "9", tone: "number" },
  { label: "÷", value: "/", tone: "operator" },
  { label: "4", value: "4", tone: "number" },
  { label: "5", value: "5", tone: "number" },
  { label: "6", value: "6", tone: "number" },
  { label: "×", value: "*", tone: "operator" },
  { label: "1", value: "1", tone: "number" },
  { label: "2", value: "2", tone: "number" },
  { label: "3", value: "3", tone: "number" },
  { label: "-", value: "-", tone: "operator" },
  { label: "0", value: "0", tone: "number" },
  { label: ".", value: ".", tone: "number" },
  { label: "=", action: "equals", tone: "operator" },
  { label: "+", value: "+", tone: "operator" },
];

function keyClass(key: CalculatorKey) {
  const base =
    "h-10 rounded border text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-cyan-400/60";

  if (key.tone === "danger") {
    return `${base} border-red-900/70 bg-red-950/40 text-red-200 hover:bg-red-900/50`;
  }

  if (key.tone === "operator") {
    return `${base} border-cyan-900/70 bg-cyan-950/30 text-cyan-200 hover:bg-cyan-900/40`;
  }

  if (key.tone === "function") {
    return `${base} border-gray-700 bg-gray-900/80 text-violet-200 hover:border-violet-700 hover:bg-violet-950/35`;
  }

  return `${base} border-gray-700 bg-gray-950/75 text-gray-100 hover:bg-gray-800`;
}

function formatHistoryTime(value: string | null) {
  if (!value) return null;

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;

  return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

export function ScientificCalculator({ open, cadernoId, questaoId, onClose }: ScientificCalculatorProps) {
  const [expression, setExpression] = useState("");
  const [result, setResult] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [history, setHistory] = useState<CalculatorHistoryItem[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;

    let active = true;
    setHistoryLoading(true);
    setHistoryError(null);

    fetchCalculatorHistory(cadernoId, questaoId)
      .then((items) => {
        if (active) setHistory(items);
      })
      .catch(() => {
        if (active) setHistoryError("Não foi possível carregar o histórico.");
      })
      .finally(() => {
        if (active) setHistoryLoading(false);
      });

    return () => {
      active = false;
    };
  }, [cadernoId, open, questaoId]);

  const appendValue = useCallback((value: string) => {
    setExpression((current) => `${current}${value}`);
    setError(null);
  }, []);

  const clear = useCallback(() => {
    setExpression("");
    setResult("");
    setError(null);
  }, []);

  const backspace = useCallback(() => {
    setExpression((current) => current.slice(0, -1));
    setError(null);
  }, []);

  const calculate = useCallback(async () => {
    const currentExpression = expression.trim();

    if (!currentExpression) {
      setResult("");
      setError("Digite uma expressão.");
      return;
    }

    let nextResult: string;

    try {
      nextResult = evaluateExpression(currentExpression);
    } catch (caught) {
      setResult("");
      setError(caught instanceof Error ? caught.message : "Não foi possível calcular.");
      return;
    }

    setResult(nextResult);
    setError(null);
    setHistoryError(null);
    setSaving(true);

    try {
      const item = await createCalculatorHistory({
        expression: currentExpression,
        result: nextResult,
        caderno_id: cadernoId,
        questao_id: questaoId,
      });
      setHistory((current) => [item, ...current]);
    } catch {
      setHistoryError("Resultado calculado, mas não foi salvo.");
    } finally {
      setSaving(false);
    }
  }, [cadernoId, expression, questaoId]);

  const handleKey = useCallback(
    (key: CalculatorKey) => {
      if ("action" in key) {
        if (key.action === "clear") clear();
        if (key.action === "backspace") backspace();
        if (key.action === "equals") void calculate();
        return;
      }

      appendValue(key.value);
    },
    [appendValue, backspace, calculate, clear],
  );

  if (!open) return null;

  return (
    <aside
      className="fixed bottom-4 left-4 right-4 z-50 flex max-h-[calc(100vh-2rem)] flex-col overflow-hidden rounded-lg border border-gray-700/80 bg-[#171717] text-gray-100 shadow-2xl shadow-black/50 sm:left-auto sm:w-[360px]"
      aria-label="Calculadora científica"
    >
      <header className="flex items-center gap-2 border-b border-gray-700/70 bg-[#111111] px-3 py-2">
        <Icon name="calculate" size={18} className="text-cyan-300" />
        <h2 className="text-sm font-semibold">Calculadora</h2>
        {saving && <span className="ml-1 text-[11px] text-gray-500">Salvando...</span>}
        <button
          type="button"
          onClick={onClose}
          className="ml-auto grid h-7 w-7 place-items-center rounded text-gray-400 transition hover:bg-gray-800 hover:text-gray-100"
          title="Fechar"
          aria-label="Fechar calculadora"
        >
          <Icon name="close" size={18} />
        </button>
      </header>

      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        <label className="block text-xs font-medium text-gray-400" htmlFor="scientific-calculator-expression">
          Expressão
        </label>
        <input
          id="scientific-calculator-expression"
          value={expression}
          onChange={(event) => {
            setExpression(event.target.value);
            setError(null);
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              void calculate();
            }
          }}
          className="h-10 w-full rounded border border-gray-700 bg-gray-950 px-3 font-mono text-sm text-gray-100 outline-none transition placeholder:text-gray-600 focus:border-cyan-500"
          placeholder="sin(30)+sqrt(16)"
          inputMode="decimal"
        />

        <div className="rounded border border-gray-700/70 bg-gray-950/70 p-3">
          <div className="text-[11px] uppercase tracking-wide text-gray-500">Resultado</div>
          <div className="mt-1 min-h-9 break-words font-mono text-3xl font-semibold text-cyan-300">
            {result || "0"}
          </div>
          {error && <div className="mt-2 text-xs text-red-300">{error}</div>}
          {historyError && <div className="mt-2 text-xs text-amber-300">{historyError}</div>}
        </div>

        <div className="grid grid-cols-4 gap-1.5">
          {KEYS.map((key) => (
            <button
              key={key.label}
              type="button"
              onClick={() => handleKey(key)}
              className={keyClass(key)}
              title={"value" in key ? key.value : key.label}
            >
              {key.label}
            </button>
          ))}
        </div>

        <section className="border-t border-gray-700/70 pt-3">
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-gray-400">Histórico</h3>
            {historyLoading && <span className="text-[11px] text-gray-500">Carregando...</span>}
          </div>

          {!historyLoading && history.length === 0 && (
            <p className="py-3 text-xs text-gray-500">Nenhum cálculo nesta questão.</p>
          )}

          <div className="space-y-1.5">
            {history.map((item) => {
              const time = formatHistoryTime(item.created_at);

              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => {
                    setExpression(item.expression);
                    setResult(item.result);
                    setError(null);
                    setHistoryError(null);
                  }}
                  className="w-full rounded border border-gray-800 bg-gray-950/40 px-2.5 py-2 text-left transition hover:border-cyan-900 hover:bg-cyan-950/20"
                >
                  <span className="flex items-center gap-2">
                    <span className="min-w-0 flex-1 truncate font-mono text-xs text-gray-300">{item.expression}</span>
                    {time && <span className="shrink-0 text-[11px] text-gray-600">{time}</span>}
                  </span>
                  <span className="mt-1 block truncate font-mono text-sm font-semibold text-cyan-300">
                    = {item.result}
                  </span>
                </button>
              );
            })}
          </div>
        </section>
      </div>
    </aside>
  );
}

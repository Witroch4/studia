"use client";

import type { KeyboardEvent } from "react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import { Icon } from "../../../../components/ds/Icon";
import { createCalculatorHistory, fetchCalculatorHistory } from "../annotations/api";
import type { CalculatorHistoryItem } from "../annotations/types";
import { CalculatorDrawArea } from "./CalculatorDrawArea";
import { evaluateExpression, type AngleMode } from "./math";
import { useDraggablePanel } from "./useDraggablePanel";

export interface ScientificCalculatorProps {
  open: boolean;
  cadernoId: number;
  questaoId: number;
  onClose: () => void;
}

type CalculatorMode = "normal" | "cientifica";

type CalculatorKey =
  | {
      label: string;
      value: string;
      ariaLabel?: string;
      tone?: "number" | "operator" | "function";
      /** Chaves que CONTINUAM a conta a partir do resultado (encadeamento ANS). */
      chains?: boolean;
      span?: 2;
    }
  | {
      label: string;
      action: "clear" | "backspace" | "equals";
      ariaLabel?: string;
      tone?: "danger" | "operator";
      span?: 2;
    };

const BASE_KEYS: CalculatorKey[] = [
  { label: "C", action: "clear", ariaLabel: "Limpar expressão", tone: "danger" },
  { label: "⌫", action: "backspace", ariaLabel: "Apagar último caractere" },
  { label: "(", value: "(", ariaLabel: "Abrir parêntese", tone: "operator" },
  { label: ")", value: ")", ariaLabel: "Fechar parêntese", tone: "operator" },
];

const SCIENTIFIC_KEYS: CalculatorKey[] = [
  { label: "sin", value: "sin(", tone: "function" },
  { label: "cos", value: "cos(", tone: "function" },
  { label: "tan", value: "tan(", tone: "function" },
  { label: "√", value: "sqrt(", ariaLabel: "Raiz quadrada", tone: "function" },
  { label: "asin", value: "asin(", ariaLabel: "Arco seno", tone: "function" },
  { label: "acos", value: "acos(", ariaLabel: "Arco cosseno", tone: "function" },
  { label: "atan", value: "atan(", ariaLabel: "Arco tangente", tone: "function" },
  { label: "x!", value: "!", ariaLabel: "Fatorial", tone: "function", chains: true },
  { label: "log", value: "log(", tone: "function" },
  { label: "ln", value: "ln(", tone: "function" },
  { label: "exp", value: "exp(", ariaLabel: "Exponencial", tone: "function" },
  { label: "^", value: "^", ariaLabel: "Potência", tone: "operator", chains: true },
  { label: "π", value: "pi", ariaLabel: "Pi", tone: "function" },
  { label: "e", value: "e", ariaLabel: "Constante de Euler", tone: "function" },
  { label: "x²", value: "^2", ariaLabel: "Elevar ao quadrado", tone: "function", chains: true },
  { label: "1/x", value: "1/(", ariaLabel: "Inverso", tone: "function" },
];

const DIGIT_KEYS: CalculatorKey[] = [
  { label: "7", value: "7", tone: "number" },
  { label: "8", value: "8", tone: "number" },
  { label: "9", value: "9", tone: "number" },
  { label: "÷", value: "/", ariaLabel: "Dividir", tone: "operator", chains: true },
  { label: "4", value: "4", tone: "number" },
  { label: "5", value: "5", tone: "number" },
  { label: "6", value: "6", tone: "number" },
  { label: "×", value: "*", ariaLabel: "Multiplicar", tone: "operator", chains: true },
  { label: "1", value: "1", tone: "number" },
  { label: "2", value: "2", tone: "number" },
  { label: "3", value: "3", tone: "number" },
  { label: "-", value: "-", ariaLabel: "Subtrair", tone: "operator", chains: true },
  { label: "0", value: "0", tone: "number" },
  { label: ".", value: ".", ariaLabel: "Ponto decimal", tone: "number" },
  { label: "=", action: "equals", ariaLabel: "Calcular resultado", tone: "operator" },
  { label: "+", value: "+", ariaLabel: "Somar", tone: "operator", chains: true },
];

const EXTRA_NORMAL_KEYS: CalculatorKey[] = [
  { label: "%", value: "%", ariaLabel: "Porcentagem", tone: "operator", chains: true, span: 2 },
  { label: "√", value: "sqrt(", ariaLabel: "Raiz quadrada", tone: "function", span: 2 },
];

const MODE_STORAGE_KEY = "studia:calc:mode";
const ANGLE_STORAGE_KEY = "studia:calc:angle";
const POSITION_STORAGE_KEY = "studia:calc:pos";

function keyClass(key: CalculatorKey) {
  const base =
    "h-10 rounded border text-sm font-medium transition focus:outline-none focus:ring-2 focus:ring-primary/60";

  if (key.tone === "danger") {
    return `${base} border-error/40 bg-error/10 text-error hover:bg-error/20`;
  }

  if (key.tone === "operator") {
    return `${base} border-primary/40 bg-primary/10 text-primary hover:bg-primary/20`;
  }

  if (key.tone === "function") {
    return `${base} border-border bg-surface/80 text-secondary hover:border-secondary/40 hover:bg-secondary/15`;
  }

  return `${base} border-border bg-page/75 text-fg hover:bg-surface-2`;
}

function formatHistoryTime(value: string | null) {
  if (!value) return null;

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return null;

  return date.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
}

function readStoredMode(): CalculatorMode {
  if (typeof window === "undefined") return "normal";
  return window.localStorage.getItem(MODE_STORAGE_KEY) === "cientifica" ? "cientifica" : "normal";
}

function readStoredAngle(): AngleMode {
  if (typeof window === "undefined") return "deg";
  return window.localStorage.getItem(ANGLE_STORAGE_KEY) === "rad" ? "rad" : "deg";
}

type BillingStatus = { plano: "free" | "pro"; is_admin: boolean; ilimitado: boolean };

export function ScientificCalculator({ open, cadernoId, questaoId, onClose }: ScientificCalculatorProps) {
  const { panelRef, position, dragging, style, dragHandleProps } = useDraggablePanel(POSITION_STORAGE_KEY);
  const contextKey = `${cadernoId}:${questaoId}`;
  const currentContextRef = useRef({ cadernoId, questaoId });
  currentContextRef.current = { cadernoId, questaoId };
  const [expression, setExpression] = useState("");
  const [result, setResult] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [historyError, setHistoryError] = useState<string | null>(null);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [history, setHistory] = useState<CalculatorHistoryItem[]>([]);
  const [pendingSaveCounts, setPendingSaveCounts] = useState<Record<string, number>>({});
  const [mode, setMode] = useState<CalculatorMode>(readStoredMode);
  const [angleMode, setAngleMode] = useState<AngleMode>(readStoredAngle);
  // Encadeamento ANS: resultado pendente p/ continuar a conta com um operador.
  const [ansPending, setAnsPending] = useState<string | null>(null);
  // Lado da gaveta = maior espaço livre; recalculado quando o drag termina.
  const [drawerSide, setDrawerSide] = useState<"left" | "right">("left");
  const saving = (pendingSaveCounts[contextKey] ?? 0) > 0;

  // Gate PRO do reconhecimento (desenhar é livre; reconhecer é PRO/admin).
  const { data: billing } = useQuery<BillingStatus>({
    queryKey: qk.billing(),
    queryFn: () => apiJson<BillingStatus>("/api/billing/status"),
    enabled: open,
    staleTime: 60_000,
  });
  const canRecognize = billing ? billing.ilimitado === true : null;

  useEffect(() => {
    if (dragging) return;
    if (!position) {
      // Posição default do CSS = canto inferior direito → gaveta abre à esquerda.
      setDrawerSide("left");
      return;
    }
    const width = panelRef.current?.offsetWidth ?? 360;
    const center = position.x + width / 2;
    setDrawerSide(center > window.innerWidth / 2 ? "left" : "right");
  }, [dragging, position, panelRef]);

  useEffect(() => {
    if (!open) return;

    let active = true;
    setHistory([]);
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

  const appendValue = useCallback(
    (value: string, chains = false) => {
      setExpression((current) => {
        if (ansPending !== null) {
          // Operador continua a conta a partir do resultado; o resto começa nova.
          return chains ? `${ansPending}${value}` : value;
        }
        return `${current}${value}`;
      });
      setAnsPending(null);
      setError(null);
    },
    [ansPending],
  );

  const clear = useCallback(() => {
    setExpression("");
    setResult("");
    setError(null);
    setAnsPending(null);
  }, []);

  const backspace = useCallback(() => {
    setExpression((current) => current.slice(0, -1));
    setError(null);
    setAnsPending(null);
  }, []);

  const calculate = useCallback(
    async (expressionOverride?: string) => {
      const currentExpression = (expressionOverride ?? expression).trim();

      if (!currentExpression) {
        setResult("");
        setError("Digite uma expressão.");
        return;
      }

      let nextResult: string;

      try {
        nextResult = evaluateExpression(currentExpression, { angleMode });
      } catch (caught) {
        setResult("");
        setError(caught instanceof Error ? caught.message : "Não foi possível calcular.");
        return;
      }

      setResult(nextResult);
      setError(null);
      setHistoryError(null);
      setAnsPending(nextResult);
      const saveContextKey = contextKey;
      setPendingSaveCounts((counts) => ({
        ...counts,
        [saveContextKey]: (counts[saveContextKey] ?? 0) + 1,
      }));

      try {
        const item = await createCalculatorHistory({
          expression: currentExpression,
          result: nextResult,
          caderno_id: cadernoId,
          questao_id: questaoId,
        });

        if (currentContextRef.current.cadernoId === cadernoId && currentContextRef.current.questaoId === questaoId) {
          setHistory((current) => [item, ...current]);
        }
      } catch {
        if (currentContextRef.current.cadernoId === cadernoId && currentContextRef.current.questaoId === questaoId) {
          setHistoryError("Resultado calculado, mas não foi salvo.");
        }
      } finally {
        setPendingSaveCounts((counts) => {
          const nextCount = Math.max(0, (counts[saveContextKey] ?? 0) - 1);
          if (nextCount > 0) return { ...counts, [saveContextKey]: nextCount };

          const nextCounts = { ...counts };
          delete nextCounts[saveContextKey];
          return nextCounts;
        });
      }
    },
    [angleMode, cadernoId, contextKey, expression, questaoId],
  );

  const handleKey = useCallback(
    (key: CalculatorKey) => {
      if ("action" in key) {
        if (key.action === "clear") clear();
        if (key.action === "backspace") backspace();
        if (key.action === "equals") void calculate();
        return;
      }

      appendValue(key.value, key.chains === true);
    },
    [appendValue, backspace, calculate, clear],
  );

  const handlePanelKeyDown = useCallback(
    (event: KeyboardEvent<HTMLElement>) => {
      if (event.key !== "Enter") return;

      const target = event.target;
      const fromPanel = target === event.currentTarget;
      const fromExpression =
        target instanceof HTMLInputElement && target.id === "scientific-calculator-expression";

      if (!fromPanel && !fromExpression) return;

      event.preventDefault();
      void calculate();
    },
    [calculate],
  );

  const switchMode = useCallback((next: CalculatorMode) => {
    setMode(next);
    try {
      window.localStorage.setItem(MODE_STORAGE_KEY, next);
    } catch {
      // preferência só não persiste
    }
  }, []);

  const toggleAngleMode = useCallback(() => {
    setAngleMode((current) => {
      const next: AngleMode = current === "deg" ? "rad" : "deg";
      try {
        window.localStorage.setItem(ANGLE_STORAGE_KEY, next);
      } catch {
        // preferência só não persiste
      }
      return next;
    });
  }, []);

  const handleDrawnExpression = useCallback(
    (drawnExpression: string) => {
      setExpression(drawnExpression);
      setAnsPending(null);
      setError(null);
      void calculate(drawnExpression);
    },
    [calculate],
  );

  if (!open) return null;

  const keys: CalculatorKey[] =
    mode === "cientifica"
      ? [...BASE_KEYS, ...SCIENTIFIC_KEYS, ...DIGIT_KEYS]
      : [...BASE_KEYS, ...DIGIT_KEYS, ...EXTRA_NORMAL_KEYS];

  return (
    <aside
      ref={panelRef as React.RefObject<HTMLElement>}
      tabIndex={-1}
      onKeyDown={handlePanelKeyDown}
      className={`fixed z-50 flex max-h-[calc(100vh-2rem)] flex-col sm:w-[360px] ${
        position ? "" : "bottom-4 left-4 right-4 sm:left-auto"
      }`}
      style={style}
      aria-label="Calculadora científica"
    >
      {/* Gaveta de desenho + alça (fora do clip do painel) */}
      <CalculatorDrawArea side={drawerSide} canRecognize={canRecognize} onExpression={handleDrawnExpression} />

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-lg border border-border/80 bg-surface text-fg shadow-2xl shadow-black/50">
        <header
          {...dragHandleProps}
          className={`flex touch-none select-none items-center gap-2 border-b border-border/70 bg-page px-3 py-2 ${
            dragging ? "cursor-grabbing" : "cursor-grab"
          }`}
        >
          <Icon name="calculate" size={18} className="text-primary" />
          <h2 className="text-sm font-semibold">Calculadora</h2>
          {saving && (
            <span className="ml-1 text-[11px] text-fg-faint" aria-live="polite" aria-atomic="true">
              Salvando…
            </span>
          )}
          <button
            type="button"
            onClick={onClose}
            className="ml-auto grid h-7 w-7 place-items-center rounded text-fg-muted transition hover:bg-surface-2 hover:text-fg"
            title="Fechar"
            aria-label="Fechar calculadora"
          >
            <Icon name="close" size={18} />
          </button>
        </header>

        <div className="flex-1 space-y-3 overflow-y-auto p-3">
          {/* Modos + DEG/RAD */}
          <div className="flex items-center gap-2">
            <div className="flex rounded border border-border bg-page/60 p-0.5" role="tablist" aria-label="Modo da calculadora">
              <button
                type="button"
                role="tab"
                aria-selected={mode === "normal"}
                onClick={() => switchMode("normal")}
                className={`rounded px-2.5 py-1 text-[11px] font-semibold transition ${
                  mode === "normal" ? "bg-primary/20 text-primary" : "text-fg-muted hover:text-fg"
                }`}
              >
                Normal
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mode === "cientifica"}
                onClick={() => switchMode("cientifica")}
                className={`rounded px-2.5 py-1 text-[11px] font-semibold transition ${
                  mode === "cientifica" ? "bg-primary/20 text-primary" : "text-fg-muted hover:text-fg"
                }`}
              >
                Científica
              </button>
            </div>
            {mode === "cientifica" && (
              <button
                type="button"
                onClick={toggleAngleMode}
                className="ml-auto rounded border border-border bg-page/60 px-2.5 py-1 text-[11px] font-semibold text-secondary transition hover:bg-surface-2"
                title="Alternar entre graus e radianos"
                aria-label={`Ângulos em ${angleMode === "deg" ? "graus" : "radianos"} — alternar`}
              >
                {angleMode === "deg" ? "DEG" : "RAD"}
              </button>
            )}
          </div>

          <label className="block text-xs font-medium text-fg-muted" htmlFor="scientific-calculator-expression">
            Expressão
          </label>
          <input
            id="scientific-calculator-expression"
            value={expression}
            onChange={(event) => {
              setExpression(event.target.value);
              setError(null);
              setAnsPending(null); // edição manual desliga o encadeamento
            }}
            className="h-10 w-full rounded border border-border bg-page px-3 font-mono text-sm text-fg outline-none transition placeholder:text-fg-faint focus:border-primary"
            placeholder="sin(30)+sqrt(16)"
            inputMode="decimal"
          />

          <div className="rounded border border-border/70 bg-page/70 p-3" aria-live="polite" aria-atomic="true">
            <div className="text-[11px] uppercase tracking-wide text-fg-faint">Resultado</div>
            <div className="mt-1 min-h-9 break-words font-mono text-3xl font-semibold text-primary">
              {result || "0"}
            </div>
            {error && <div className="mt-2 text-xs text-error">{error}</div>}
            {historyError && <div className="mt-2 text-xs text-warning">{historyError}</div>}
          </div>

          <div className="grid grid-cols-4 gap-1.5">
            {keys.map((key) => (
              <button
                key={`${mode}-${key.label}`}
                type="button"
                onClick={() => {
                  handleKey(key);
                  panelRef.current?.focus({ preventScroll: true });
                }}
                className={`${keyClass(key)} ${key.span === 2 ? "col-span-2" : ""}`}
                title={key.ariaLabel ?? ("value" in key ? key.value : key.label)}
                aria-label={key.ariaLabel}
              >
                {key.label}
              </button>
            ))}
          </div>

          <section className="border-t border-border/70 pt-3">
            <div className="mb-2 flex items-center justify-between">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-fg-muted">Histórico</h3>
              {historyLoading && (
                <span className="text-[11px] text-fg-faint" aria-live="polite" aria-atomic="true">
                  Carregando…
                </span>
              )}
            </div>

            {!historyLoading && history.length === 0 && (
              <p className="py-3 text-xs text-fg-faint">Nenhum cálculo nesta questão.</p>
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
                      // Restaurar do histórico também arma o encadeamento ANS.
                      setAnsPending(item.result);
                    }}
                    className="w-full rounded border border-border bg-page/40 px-2.5 py-2 text-left transition hover:border-primary/40 hover:bg-primary/10"
                  >
                    <span className="flex items-center gap-2">
                      <span className="min-w-0 flex-1 truncate font-mono text-xs text-fg">{item.expression}</span>
                      {time && <span className="shrink-0 text-[11px] text-fg-faint">{time}</span>}
                    </span>
                    <span className="mt-1 block truncate font-mono text-sm font-semibold text-primary">
                      = {item.result}
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        </div>
      </div>
    </aside>
  );
}

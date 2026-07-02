"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type PointerEvent } from "react";
import { BrandLoader } from "../../../../components/ds/BrandLoader";
import { Icon } from "../../../../components/ds/Icon";
import { reconhecerDesenho } from "../annotations/api";

export interface CalculatorDrawAreaProps {
  /** Lado onde a gaveta abre (maior espaço livre em relação ao painel). */
  side: "left" | "right";
  /** PRO/admin pode reconhecer; null = billing ainda carregando. */
  canRecognize: boolean | null;
  /** Recebe a expressão transcrita (preenche o campo e calcula). */
  onExpression: (expression: string) => void;
}

type DrawPoint = { x: number; y: number };
type DrawStroke = DrawPoint[];

const DRAWER_WIDTH = 288;
const HANDLE_GAP = 26; // espaço da alça entre o painel e a gaveta
const AUTO_DEBOUNCE_MS = 1500;
const AUTO_STORAGE_KEY = "studia:calc:draw-auto";
const STROKE_WIDTH = 3;

function readAutoPref(): boolean {
  if (typeof window === "undefined") return true;
  return window.localStorage.getItem(AUTO_STORAGE_KEY) !== "off";
}

/** Exporta os traços como PNG p/ visão do modelo: traço escuro em fundo BRANCO. */
function exportStrokesPng(strokes: DrawStroke[], width: number, height: number): string {
  const scale = 2; // nitidez para o OCR do modelo
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(1, Math.round(width * scale));
  canvas.height = Math.max(1, Math.round(height * scale));
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("canvas 2d indisponível");

  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.strokeStyle = "#111111";
  ctx.fillStyle = "#111111";
  ctx.lineWidth = STROKE_WIDTH * scale;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";

  for (const stroke of strokes) {
    if (stroke.length === 0) continue;
    const first = { x: stroke[0].x * canvas.width, y: stroke[0].y * canvas.height };
    if (stroke.length === 1) {
      ctx.beginPath();
      ctx.arc(first.x, first.y, (STROKE_WIDTH * scale) / 2, 0, Math.PI * 2);
      ctx.fill();
      continue;
    }
    ctx.beginPath();
    ctx.moveTo(first.x, first.y);
    for (const point of stroke.slice(1)) {
      ctx.lineTo(point.x * canvas.width, point.y * canvas.height);
    }
    ctx.stroke();
  }

  return canvas.toDataURL("image/png").split(",")[1];
}

export function CalculatorDrawArea({ side, canRecognize, onExpression }: CalculatorDrawAreaProps) {
  const [open, setOpen] = useState(false);
  const [auto, setAuto] = useState(readAutoPref);
  const [strokes, setStrokes] = useState<DrawStroke[]>([]);
  const [recognizing, setRecognizing] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const strokesRef = useRef<DrawStroke[]>(strokes);
  strokesRef.current = strokes;
  const currentStroke = useRef<DrawStroke | null>(null);
  const activePointerId = useRef<number | null>(null);
  const autoTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Evita reenvio se nada mudou desde o último reconhecimento.
  const lastRecognizedSignature = useRef<string | null>(null);
  const recognizingRef = useRef(false);
  recognizingRef.current = recognizing;

  const signature = useMemo(
    () => `${strokes.length}:${strokes.reduce((acc, s) => acc + s.length, 0)}`,
    [strokes],
  );

  const redraw = useCallback(() => {
    const node = canvasRef.current;
    const ctx = node?.getContext("2d");
    if (!node || !ctx) return;

    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const width = node.width / dpr;
    const height = node.height / dpr;
    ctx.clearRect(0, 0, width, height);
    // Traço claro na UI (tema dark); a exportação re-renderiza escuro no branco.
    ctx.strokeStyle = "#e2e8f0";
    ctx.fillStyle = "#e2e8f0";
    ctx.lineWidth = STROKE_WIDTH;
    ctx.lineCap = "round";
    ctx.lineJoin = "round";

    const all = currentStroke.current
      ? [...strokesRef.current, currentStroke.current]
      : strokesRef.current;
    for (const stroke of all) {
      if (stroke.length === 0) continue;
      const first = { x: stroke[0].x * width, y: stroke[0].y * height };
      if (stroke.length === 1) {
        ctx.beginPath();
        ctx.arc(first.x, first.y, STROKE_WIDTH / 2, 0, Math.PI * 2);
        ctx.fill();
        continue;
      }
      ctx.beginPath();
      ctx.moveTo(first.x, first.y);
      for (const point of stroke.slice(1)) {
        ctx.lineTo(point.x * width, point.y * height);
      }
      ctx.stroke();
    }
  }, []);

  // Dimensiona o canvas ao container (com DPR) e re-renderiza.
  useEffect(() => {
    if (!open) return;
    const node = canvasRef.current;
    const parent = node?.parentElement;
    if (!node || !parent) return;

    const resize = () => {
      const rect = parent.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      node.width = Math.max(1, Math.round(rect.width * dpr));
      node.height = Math.max(1, Math.round(rect.height * dpr));
      node.style.width = `${rect.width}px`;
      node.style.height = `${rect.height}px`;
      redraw();
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(parent);
    return () => observer.disconnect();
  }, [open, redraw]);

  useEffect(() => {
    redraw();
  }, [strokes, redraw]);

  const recognize = useCallback(async () => {
    const currentStrokes = strokesRef.current;
    if (recognizingRef.current || currentStrokes.length === 0) return;

    const node = canvasRef.current;
    if (!node) return;
    const dpr = window.devicePixelRatio || 1;

    const sig = `${currentStrokes.length}:${currentStrokes.reduce((acc, s) => acc + s.length, 0)}`;
    if (sig === lastRecognizedSignature.current) return;

    setRecognizing(true);
    setMessage(null);
    try {
      const png = exportStrokesPng(currentStrokes, node.width / dpr, node.height / dpr);
      const expression = await reconhecerDesenho(png);
      lastRecognizedSignature.current = sig;
      onExpression(expression);
    } catch (caught) {
      const err = caught as Error & { status?: number; detail?: string };
      if (err.status === 422) {
        setMessage("Não entendi o desenho — ajuste e tente de novo.");
        lastRecognizedSignature.current = sig; // não re-tentar sozinho o mesmo desenho
      } else if (err.status === 403) {
        setMessage("Recurso PRO — assine para reconhecer seu desenho.");
      } else if (err.status === 413) {
        setMessage("Desenho grande demais — limpe e tente de novo.");
      } else {
        setMessage("IA indisponível no momento.");
      }
    } finally {
      setRecognizing(false);
    }
  }, [onExpression]);

  const scheduleAutoRecognize = useCallback(() => {
    if (!auto || canRecognize !== true) return;
    if (autoTimer.current) clearTimeout(autoTimer.current);
    autoTimer.current = setTimeout(() => {
      autoTimer.current = null;
      void recognize();
    }, AUTO_DEBOUNCE_MS);
  }, [auto, canRecognize, recognize]);

  const cancelAutoRecognize = useCallback(() => {
    if (autoTimer.current) {
      clearTimeout(autoTimer.current);
      autoTimer.current = null;
    }
  }, []);

  useEffect(() => () => cancelAutoRecognize(), [cancelAutoRecognize]);

  const pointFromEvent = useCallback((event: PointerEvent<HTMLCanvasElement>): DrawPoint => {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: Math.min(1, Math.max(0, (event.clientX - rect.left) / Math.max(1, rect.width))),
      y: Math.min(1, Math.max(0, (event.clientY - rect.top) / Math.max(1, rect.height))),
    };
  }, []);

  const handlePointerDown = useCallback(
    (event: PointerEvent<HTMLCanvasElement>) => {
      if (activePointerId.current !== null) return;
      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      activePointerId.current = event.pointerId;
      cancelAutoRecognize(); // novo traço cancela envio pendente
      currentStroke.current = [pointFromEvent(event)];
      redraw();
    },
    [cancelAutoRecognize, pointFromEvent, redraw],
  );

  const handlePointerMove = useCallback(
    (event: PointerEvent<HTMLCanvasElement>) => {
      if (activePointerId.current !== event.pointerId || !currentStroke.current) return;
      event.preventDefault();
      currentStroke.current.push(pointFromEvent(event));
      redraw();
    },
    [pointFromEvent, redraw],
  );

  const handlePointerUp = useCallback(
    (event: PointerEvent<HTMLCanvasElement>) => {
      if (activePointerId.current !== event.pointerId) return;
      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      activePointerId.current = null;
      const stroke = currentStroke.current;
      currentStroke.current = null;
      if (stroke && stroke.length > 0) {
        setStrokes((current) => [...current, stroke]);
        setMessage(null);
        scheduleAutoRecognize();
      }
    },
    [scheduleAutoRecognize],
  );

  const undo = useCallback(() => {
    cancelAutoRecognize();
    setStrokes((current) => current.slice(0, -1));
    setMessage(null);
  }, [cancelAutoRecognize]);

  const clear = useCallback(() => {
    cancelAutoRecognize();
    setStrokes([]);
    setMessage(null);
    lastRecognizedSignature.current = null;
  }, [cancelAutoRecognize]);

  const toggleAuto = useCallback(() => {
    setAuto((current) => {
      const next = !current;
      try {
        window.localStorage.setItem(AUTO_STORAGE_KEY, next ? "on" : "off");
      } catch {
        // preferência só não persiste
      }
      if (!next) cancelAutoRecognize();
      return next;
    });
  }, [cancelAutoRecognize]);

  const hasUnrecognized = strokes.length > 0 && signature !== lastRecognizedSignature.current;

  return (
    <>
      {/* Alça saliente: segure/clique para abrir a gaveta de desenho */}
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        className={`absolute top-1/2 z-10 flex h-24 w-6 -translate-y-1/2 flex-col items-center justify-center gap-1 rounded border border-border/80 bg-surface text-fg-muted shadow-lg shadow-black/40 transition hover:bg-surface-2 hover:text-primary ${
          side === "left" ? "-left-6 rounded-r-none border-r-0" : "-right-6 rounded-l-none border-l-0"
        }`}
        title={open ? "Fechar área de desenho" : "Desenhar a conta"}
        aria-label={open ? "Fechar área de desenho" : "Abrir área de desenho"}
        aria-expanded={open}
      >
        <Icon name="stylus" size={15} />
        {/* ranhuras de pegador */}
        <span className="flex flex-col gap-0.5" aria-hidden>
          <span className="h-px w-3 bg-border" />
          <span className="h-px w-3 bg-border" />
          <span className="h-px w-3 bg-border" />
        </span>
      </button>

      {/* Gaveta pull-out (desliza colada à lateral do painel) */}
      <div
        className={`pointer-events-none absolute top-0 bottom-0 overflow-hidden ${
          side === "left" ? "right-full" : "left-full"
        }`}
        style={{ width: DRAWER_WIDTH, [side === "left" ? "marginRight" : "marginLeft"]: HANDLE_GAP } as never}
        aria-hidden={!open}
      >
        <div
          className={`pointer-events-auto flex h-full flex-col overflow-hidden rounded-lg border border-border/80 bg-surface shadow-2xl shadow-black/50 transition-transform duration-300 ${
            open ? "translate-x-0" : side === "left" ? "translate-x-[calc(100%+16px)]" : "-translate-x-[calc(100%+16px)]"
          }`}
        >
          <header className="flex items-center gap-2 border-b border-border/70 bg-page px-3 py-2">
            <Icon name="stylus" size={16} className="text-primary" />
            <h3 className="text-xs font-semibold">Desenhe a conta</h3>
            <div className="ml-auto flex items-center gap-1">
              <button
                type="button"
                onClick={undo}
                disabled={strokes.length === 0}
                className="grid h-6 w-6 place-items-center rounded text-fg-muted transition hover:bg-surface-2 hover:text-fg disabled:opacity-40"
                title="Desfazer traço"
                aria-label="Desfazer último traço"
              >
                <Icon name="undo" size={15} />
              </button>
              <button
                type="button"
                onClick={clear}
                disabled={strokes.length === 0}
                className="grid h-6 w-6 place-items-center rounded text-fg-muted transition hover:bg-surface-2 hover:text-fg disabled:opacity-40"
                title="Limpar tudo"
                aria-label="Limpar desenho"
              >
                <Icon name="delete" size={15} />
              </button>
            </div>
          </header>

          <div className="relative min-h-0 flex-1 bg-page/60">
            <canvas
              ref={canvasRef}
              className="absolute inset-0 touch-none cursor-crosshair"
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={handlePointerUp}
              onPointerCancel={handlePointerUp}
              role="application"
              aria-label="Área de desenho da expressão"
            />
            {strokes.length === 0 && !currentStroke.current && (
              <p className="pointer-events-none absolute inset-x-3 top-1/2 -translate-y-1/2 text-center text-[11px] leading-relaxed text-fg-faint">
                Desenhe a conta à mão — a IA transcreve para a calculadora.
              </p>
            )}
          </div>

          {/* Rodapé: espaço RESERVADO (status/controles trocam sem pular layout) */}
          <footer className="min-h-[64px] border-t border-border/70 bg-page px-3 py-2">
            {canRecognize === false ? (
              <div className="flex items-center gap-2">
                <Icon name="lock" size={16} className="shrink-0 text-warning" />
                <p className="text-[11px] leading-tight text-fg-muted">
                  Recurso PRO —{" "}
                  <Link href="/assinar" className="font-semibold text-primary hover:underline">
                    assine para reconhecer seu desenho
                  </Link>
                  . Desenhar é livre.
                </p>
              </div>
            ) : recognizing ? (
              <div className="flex items-center justify-center gap-2 py-1">
                <BrandLoader label="Reconhecendo…" size={22} className="!flex-row !gap-2" />
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <button
                  type="button"
                  onClick={toggleAuto}
                  role="switch"
                  aria-checked={auto}
                  className={`relative h-5 w-9 shrink-0 rounded-full border transition ${
                    auto ? "border-primary/60 bg-primary/30" : "border-border bg-surface-2"
                  }`}
                  title="Reconhecer automaticamente ao parar de desenhar"
                >
                  <span
                    className={`absolute top-0.5 h-3.5 w-3.5 rounded-full transition-all ${
                      auto ? "left-[18px] bg-primary" : "left-0.5 bg-fg-faint"
                    }`}
                  />
                </button>
                <span className="text-[11px] text-fg-muted">Auto</span>
                <button
                  type="button"
                  onClick={() => void recognize()}
                  disabled={canRecognize !== true || !hasUnrecognized}
                  className="ml-auto rounded border border-primary/40 bg-primary/10 px-2.5 py-1 text-[11px] font-semibold text-primary transition hover:bg-primary/20 disabled:opacity-40"
                >
                  Reconhecer
                </button>
              </div>
            )}
            {message && <p className="mt-1.5 text-[11px] text-warning">{message}</p>}
          </footer>
        </div>
      </div>
    </>
  );
}

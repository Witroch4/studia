"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties, type PointerEvent } from "react";

export interface PanelPosition {
  x: number;
  y: number;
}

const VIEWPORT_MARGIN = 8;

function readStoredPosition(storageKey: string): PanelPosition | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(storageKey);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as PanelPosition;
    if (typeof parsed?.x !== "number" || typeof parsed?.y !== "number") return null;
    return parsed;
  } catch {
    return null;
  }
}

function clampToViewport(pos: PanelPosition, panel: HTMLElement | null): PanelPosition {
  const width = panel?.offsetWidth ?? 360;
  const height = panel?.offsetHeight ?? 200;
  const maxX = Math.max(VIEWPORT_MARGIN, window.innerWidth - width - VIEWPORT_MARGIN);
  const maxY = Math.max(VIEWPORT_MARGIN, window.innerHeight - height - VIEWPORT_MARGIN);
  return {
    x: Math.min(maxX, Math.max(VIEWPORT_MARGIN, pos.x)),
    y: Math.min(maxY, Math.max(VIEWPORT_MARGIN, pos.y)),
  };
}

/**
 * Painel flutuante arrastável pelo cabeçalho (pointer events + capture).
 *
 * `position === null` → o painel fica na posição default do CSS (ex.:
 * bottom-right); ao primeiro arrasto passa a ser posicionado por
 * `transform: translate(x, y)` a partir do canto superior esquerdo, com clamp
 * ao viewport (inclusive em resize) e persistência em localStorage.
 */
export function useDraggablePanel(storageKey: string) {
  const panelRef = useRef<HTMLElement | null>(null);
  const [position, setPosition] = useState<PanelPosition | null>(null);
  const [dragging, setDragging] = useState(false);
  const dragState = useRef<{ pointerId: number; offsetX: number; offsetY: number } | null>(null);

  // Posição persistida entra só no client (evita mismatch de hydration).
  useEffect(() => {
    const stored = readStoredPosition(storageKey);
    if (stored) setPosition(clampToViewport(stored, panelRef.current));
  }, [storageKey]);

  // Janela redimensionou → painel não pode ficar fora da tela.
  useEffect(() => {
    const onResize = () => {
      setPosition((current) => (current ? clampToViewport(current, panelRef.current) : current));
    };
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const persist = useCallback(
    (pos: PanelPosition) => {
      try {
        window.localStorage.setItem(storageKey, JSON.stringify(pos));
      } catch {
        // storage cheio/bloqueado: posição só não persiste entre visitas
      }
    },
    [storageKey],
  );

  const handleDragPointerDown = useCallback((event: PointerEvent<HTMLElement>) => {
    // Botões/inputs dentro do cabeçalho continuam clicáveis.
    if ((event.target as HTMLElement).closest("button, input, select, a")) return;

    const panel = panelRef.current;
    if (!panel) return;

    const rect = panel.getBoundingClientRect();
    event.preventDefault();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragState.current = {
      pointerId: event.pointerId,
      offsetX: event.clientX - rect.left,
      offsetY: event.clientY - rect.top,
    };
    setDragging(true);
    // Sai do posicionamento CSS default e congela a posição atual.
    setPosition(clampToViewport({ x: rect.left, y: rect.top }, panel));
  }, []);

  const handleDragPointerMove = useCallback((event: PointerEvent<HTMLElement>) => {
    const state = dragState.current;
    if (!state || state.pointerId !== event.pointerId) return;

    event.preventDefault();
    setPosition(
      clampToViewport(
        { x: event.clientX - state.offsetX, y: event.clientY - state.offsetY },
        panelRef.current,
      ),
    );
  }, []);

  const handleDragPointerUp = useCallback(
    (event: PointerEvent<HTMLElement>) => {
      const state = dragState.current;
      if (!state || state.pointerId !== event.pointerId) return;

      if (event.currentTarget.hasPointerCapture(event.pointerId)) {
        event.currentTarget.releasePointerCapture(event.pointerId);
      }
      dragState.current = null;
      setDragging(false);
      setPosition((current) => {
        if (current) persist(current);
        return current;
      });
    },
    [persist],
  );

  const style: CSSProperties | undefined = position
    ? { top: 0, left: 0, right: "auto", bottom: "auto", transform: `translate(${position.x}px, ${position.y}px)` }
    : undefined;

  return {
    panelRef,
    position,
    dragging,
    style,
    dragHandleProps: {
      onPointerDown: handleDragPointerDown,
      onPointerMove: handleDragPointerMove,
      onPointerUp: handleDragPointerUp,
      onPointerCancel: handleDragPointerUp,
    },
  };
}

"use client";

import { useCallback, useEffect, useRef, useState, type PointerEvent } from "react";
import type { CanvasPoint, CanvasState, CanvasStroke, CanvasTool } from "../annotations/types";

interface QuestionCanvasOverlayProps {
  active: boolean;
  canvas: CanvasState;
  tool: CanvasTool;
  color: string;
  width: number;
  onChange: (updater: (current: CanvasState) => CanvasState) => void;
}

type CanvasSize = { width: number; height: number };

const MIN_CANVAS_SIZE: CanvasSize = { width: 1, height: 1 };

function clamp01(value: number) {
  return Math.min(1, Math.max(0, value));
}

function makeStroke(
  tool: Exclude<CanvasTool, "eraser">,
  color: string,
  width: number,
  point: CanvasPoint,
): CanvasStroke {
  const suffix =
    typeof crypto !== "undefined" && "randomUUID" in crypto
      ? crypto.randomUUID()
      : `${Date.now()}_${Math.random().toString(36).slice(2)}`;

  return {
    id: `stroke_${suffix}`,
    tool,
    color,
    width,
    points: [point],
  };
}

function toCanvasPoint(point: CanvasPoint, size: CanvasSize) {
  return {
    x: point.x * size.width,
    y: point.y * size.height,
  };
}

function configureStroke(ctx: CanvasRenderingContext2D, stroke: CanvasStroke) {
  ctx.globalAlpha = stroke.tool === "highlight" ? 0.35 : 1;
  ctx.strokeStyle = stroke.color;
  ctx.fillStyle = stroke.color;
  ctx.lineWidth = stroke.width;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
}

function drawStroke(ctx: CanvasRenderingContext2D, stroke: CanvasStroke, size: CanvasSize) {
  if (stroke.points.length === 0) return;

  configureStroke(ctx, stroke);
  const first = toCanvasPoint(stroke.points[0], size);

  if (stroke.points.length === 1) {
    ctx.beginPath();
    ctx.arc(first.x, first.y, Math.max(1, stroke.width / 2), 0, Math.PI * 2);
    ctx.fill();
    return;
  }

  ctx.beginPath();
  ctx.moveTo(first.x, first.y);
  for (const point of stroke.points.slice(1)) {
    const next = toCanvasPoint(point, size);
    ctx.lineTo(next.x, next.y);
  }
  ctx.stroke();
}

function drawSegment(
  ctx: CanvasRenderingContext2D,
  stroke: CanvasStroke,
  from: CanvasPoint,
  to: CanvasPoint,
  size: CanvasSize,
) {
  configureStroke(ctx, stroke);
  const start = toCanvasPoint(from, size);
  const end = toCanvasPoint(to, size);
  ctx.beginPath();
  ctx.moveTo(start.x, start.y);
  ctx.lineTo(end.x, end.y);
  ctx.stroke();
}

function segmentDistance(point: CanvasPoint, start: CanvasPoint, end: CanvasPoint, size: CanvasSize) {
  const p = toCanvasPoint(point, size);
  const a = toCanvasPoint(start, size);
  const b = toCanvasPoint(end, size);
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const lengthSquared = dx * dx + dy * dy;

  if (lengthSquared === 0) return Math.hypot(p.x - a.x, p.y - a.y);

  const t = Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / lengthSquared));
  const x = a.x + t * dx;
  const y = a.y + t * dy;
  return Math.hypot(p.x - x, p.y - y);
}

function distanceToStroke(point: CanvasPoint, stroke: CanvasStroke, size: CanvasSize) {
  if (stroke.points.length === 0) return Number.POSITIVE_INFINITY;
  if (stroke.points.length === 1) {
    const p = toCanvasPoint(point, size);
    const only = toCanvasPoint(stroke.points[0], size);
    return Math.hypot(p.x - only.x, p.y - only.y);
  }

  let shortest = Number.POSITIVE_INFINITY;
  for (let index = 1; index < stroke.points.length; index += 1) {
    shortest = Math.min(shortest, segmentDistance(point, stroke.points[index - 1], stroke.points[index], size));
  }
  return shortest;
}

export function QuestionCanvasOverlay({ active, canvas, tool, color, width, onChange }: QuestionCanvasOverlayProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const sizeRef = useRef<CanvasSize>(MIN_CANVAS_SIZE);
  const currentStroke = useRef<CanvasStroke | null>(null);
  const activePointerId = useRef<number | null>(null);
  const [size, setSize] = useState<CanvasSize>(MIN_CANVAS_SIZE);

  const getContext = useCallback(() => {
    const node = canvasRef.current;
    if (!node) return null;

    const ctx = node.getContext("2d");
    if (!ctx) return null;

    const dpr = window.devicePixelRatio || 1;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return ctx;
  }, []);

  const redraw = useCallback(() => {
    const node = canvasRef.current;
    const ctx = getContext();
    if (!node || !ctx) return;

    const dpr = window.devicePixelRatio || 1;
    ctx.clearRect(0, 0, node.width / dpr, node.height / dpr);
    ctx.save();
    for (const stroke of canvas.strokes) {
      drawStroke(ctx, stroke, sizeRef.current);
    }
    if (currentStroke.current) {
      drawStroke(ctx, currentStroke.current, sizeRef.current);
    }
    ctx.restore();
  }, [canvas.strokes, getContext]);

  useEffect(() => {
    const node = canvasRef.current;
    const parent = node?.parentElement;
    if (!node || !parent) return;

    const resize = () => {
      const rect = parent.getBoundingClientRect();
      const nextSize = {
        width: Math.max(1, rect.width),
        height: Math.max(1, rect.height),
      };
      const dpr = window.devicePixelRatio || 1;
      node.width = Math.max(1, Math.round(nextSize.width * dpr));
      node.height = Math.max(1, Math.round(nextSize.height * dpr));
      node.style.width = `${nextSize.width}px`;
      node.style.height = `${nextSize.height}px`;
      sizeRef.current = nextSize;
      setSize(nextSize);
    };

    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(parent);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    redraw();
  }, [redraw, size]);

  useEffect(() => {
    if (active) return;
    currentStroke.current = null;
    activePointerId.current = null;
  }, [active]);

  const pointFromEvent = useCallback((event: PointerEvent<HTMLCanvasElement>): CanvasPoint => {
    const rect = event.currentTarget.getBoundingClientRect();
    return {
      x: clamp01((event.clientX - rect.left) / Math.max(1, rect.width)),
      y: clamp01((event.clientY - rect.top) / Math.max(1, rect.height)),
      p: event.pressure || 0.5,
    };
  }, []);

  const eraseAtPoint = useCallback(
    (point: CanvasPoint) => {
      const eraseRadius = Math.max(12, width * 1.75);
      const currentSize = sizeRef.current;
      onChange((current) => ({
        version: 1,
        cardSize: { width: currentSize.width, height: currentSize.height },
        strokes: current.strokes.filter((stroke) => distanceToStroke(point, stroke, currentSize) > eraseRadius),
      }));
    },
    [onChange, width],
  );

  const handlePointerDown = useCallback(
    (event: PointerEvent<HTMLCanvasElement>) => {
      if (!active) return;

      event.preventDefault();
      event.currentTarget.setPointerCapture(event.pointerId);
      activePointerId.current = event.pointerId;

      const point = pointFromEvent(event);
      if (tool === "eraser") {
        eraseAtPoint(point);
        return;
      }

      const stroke = makeStroke(tool, color, width, point);
      currentStroke.current = stroke;

      const ctx = getContext();
      if (!ctx) return;

      ctx.save();
      drawStroke(ctx, stroke, sizeRef.current);
      ctx.restore();
    },
    [active, color, eraseAtPoint, getContext, pointFromEvent, tool, width],
  );

  const handlePointerMove = useCallback(
    (event: PointerEvent<HTMLCanvasElement>) => {
      if (!active || activePointerId.current !== event.pointerId) return;

      event.preventDefault();
      const point = pointFromEvent(event);

      if (tool === "eraser") {
        eraseAtPoint(point);
        return;
      }

      const stroke = currentStroke.current;
      if (!stroke) return;

      const previous = stroke.points[stroke.points.length - 1];
      stroke.points.push(point);

      const ctx = getContext();
      if (!ctx) return;

      ctx.save();
      drawSegment(ctx, stroke, previous, point, sizeRef.current);
      ctx.restore();
    },
    [active, eraseAtPoint, getContext, pointFromEvent, tool],
  );

  const finishStroke = useCallback(
    (event?: PointerEvent<HTMLCanvasElement>) => {
      if (event && activePointerId.current !== event.pointerId) return;

      if (event) {
        event.preventDefault();
        if (event.currentTarget.hasPointerCapture(event.pointerId)) {
          event.currentTarget.releasePointerCapture(event.pointerId);
        }
      }

      activePointerId.current = null;
      const stroke = currentStroke.current;
      currentStroke.current = null;

      if (!stroke) return;

      const currentSize = sizeRef.current;
      onChange((current) => ({
        version: 1,
        cardSize: { width: currentSize.width, height: currentSize.height },
        strokes: [...current.strokes, stroke],
      }));
    },
    [onChange],
  );

  return (
    <canvas
      ref={canvasRef}
      className={`absolute inset-0 z-20 rounded-lg touch-none ${
        active ? "cursor-crosshair bg-cyan-500/[0.02]" : "pointer-events-none hidden"
      }`}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={finishStroke}
      onPointerCancel={finishStroke}
      aria-hidden={!active}
    />
  );
}

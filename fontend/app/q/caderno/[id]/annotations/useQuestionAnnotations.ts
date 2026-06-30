"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Dispatch, SetStateAction } from "react";
import { fetchAnnotations, saveAnnotations } from "./api";
import type { CanvasState, StrikeTarget, StrikesState } from "./types";
import { emptyCanvas, emptyStrikes } from "./types";

interface StoredAnnotations {
  canvas_json: CanvasState;
  strikes_json: StrikesState;
}

interface QuestionKey {
  cadernoId: number;
  questaoId: number;
  key: string;
}

interface PendingSave extends QuestionKey {
  canvas: CanvasState;
  strikes: StrikesState;
}

function keyFor(cadernoId: number, questaoId: number) {
  return `studia:q:${cadernoId}:${questaoId}:annotations`;
}

function payloadFor(canvas: CanvasState, strikes: StrikesState): StoredAnnotations {
  return { canvas_json: canvas, strikes_json: strikes };
}

function parseStoredAnnotations(raw: string): StoredAnnotations {
  const parsed = JSON.parse(raw) as Partial<StoredAnnotations>;
  return {
    canvas_json: parsed.canvas_json || emptyCanvas(),
    strikes_json: parsed.strikes_json || emptyStrikes(),
  };
}

function hasTarget(targets: StrikeTarget[], target: StrikeTarget) {
  return targets.some((item) => {
    if (item.type !== target.type) return false;
    if (item.type === "alternative" && target.type === "alternative") return item.id === target.id;
    if (item.type === "statement-block" && target.type === "statement-block") return item.index === target.index;
    return false;
  });
}

export function useQuestionAnnotations(cadernoId: number | null, questaoId: number | null) {
  const [canvas, setCanvasState] = useState<CanvasState>(emptyCanvas);
  const [strikes, setStrikesState] = useState<StrikesState>(emptyStrikes);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const canvasRef = useRef<CanvasState>(emptyCanvas());
  const strikesRef = useRef<StrikesState>(emptyStrikes());
  const saveTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const mutationRevisions = useRef<Map<string, number>>(new Map());
  const savingCount = useRef(0);
  const currentQuestion = useMemo<QuestionKey | null>(
    () => (cadernoId != null && questaoId != null ? { cadernoId, questaoId, key: keyFor(cadernoId, questaoId) } : null),
    [cadernoId, questaoId],
  );

  const setAnnotationState = useCallback((nextCanvas: CanvasState, nextStrikes: StrikesState) => {
    canvasRef.current = nextCanvas;
    strikesRef.current = nextStrikes;
    setCanvasState(nextCanvas);
    setStrikesState(nextStrikes);
  }, []);

  const setCanvas: Dispatch<SetStateAction<CanvasState>> = useCallback((value) => {
    const next = typeof value === "function" ? value(canvasRef.current) : value;
    canvasRef.current = next;
    setCanvasState(next);
  }, []);

  const flushPayload = useCallback(async (pending: PendingSave) => {
    const payload = payloadFor(pending.canvas, pending.strikes);
    savingCount.current += 1;
    setSaving(true);
    setSaveError(null);
    try {
      await saveAnnotations(pending.cadernoId, pending.questaoId, pending.canvas, pending.strikes);
      if (localStorage.getItem(pending.key) === JSON.stringify(payload)) {
        localStorage.removeItem(pending.key);
      }
    } catch (error) {
      localStorage.setItem(pending.key, JSON.stringify(payload));
      setSaveError(error instanceof Error ? error.message : "Falha ao salvar anotacoes");
    } finally {
      savingCount.current = Math.max(0, savingCount.current - 1);
      setSaving(savingCount.current > 0);
    }
  }, []);

  useEffect(() => {
    if (!currentQuestion) {
      setAnnotationState(emptyCanvas(), emptyStrikes());
      setLoading(false);
      return;
    }

    let cancelled = false;
    const { cadernoId: currentCadernoId, questaoId: currentQuestaoId, key } = currentQuestion;
    setLoading(true);
    setSaveError(null);

    const localRaw = localStorage.getItem(key);
    if (localRaw) {
      try {
        const local = parseStoredAnnotations(localRaw);
        setAnnotationState(local.canvas_json, local.strikes_json);
      } catch {
        localStorage.removeItem(key);
        setAnnotationState(emptyCanvas(), emptyStrikes());
      }
    } else {
      setAnnotationState(emptyCanvas(), emptyStrikes());
    }

    const fetchRevision = mutationRevisions.current.get(key) ?? 0;

    fetchAnnotations(currentCadernoId, currentQuestaoId)
      .then((data) => {
        if (cancelled) return;
        const pendingRaw = localStorage.getItem(key);
        if (pendingRaw) {
          try {
            const pending = parseStoredAnnotations(pendingRaw);
            setAnnotationState(pending.canvas_json, pending.strikes_json);
            return;
          } catch {
            localStorage.removeItem(key);
            setAnnotationState(emptyCanvas(), emptyStrikes());
          }
        }
        if ((mutationRevisions.current.get(key) ?? 0) !== fetchRevision) return;
        setAnnotationState(data.canvas_json || emptyCanvas(), data.strikes_json || emptyStrikes());
      })
      .catch((error) => {
        if (!cancelled) setSaveError(error instanceof Error ? error.message : "Falha ao carregar anotacoes");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [currentQuestion, setAnnotationState]);

  const scheduleSave = useCallback(
    (nextCanvas: CanvasState, nextStrikes: StrikesState) => {
      if (!currentQuestion) return;
      const pending: PendingSave = { ...currentQuestion, canvas: nextCanvas, strikes: nextStrikes };
      const payload = payloadFor(nextCanvas, nextStrikes);
      mutationRevisions.current.set(pending.key, (mutationRevisions.current.get(pending.key) ?? 0) + 1);
      localStorage.setItem(pending.key, JSON.stringify(payload));

      const currentTimer = saveTimers.current.get(pending.key);
      if (currentTimer) clearTimeout(currentTimer);
      const nextTimer = setTimeout(() => {
        saveTimers.current.delete(pending.key);
        void flushPayload(pending);
      }, 700);
      saveTimers.current.set(pending.key, nextTimer);
    },
    [currentQuestion, flushPayload],
  );

  const updateCanvas = useCallback(
    (updater: (current: CanvasState) => CanvasState) => {
      const next = updater(canvasRef.current);
      canvasRef.current = next;
      setCanvasState(next);
      scheduleSave(next, strikesRef.current);
    },
    [scheduleSave],
  );

  const toggleStrike = useCallback(
    (target: StrikeTarget) => {
      const current = strikesRef.current;
      const nextTargets = hasTarget(current.targets, target)
        ? current.targets.filter((item) => !hasTarget([item], target))
        : [...current.targets, target];
      const next = { version: 1 as const, targets: nextTargets };
      strikesRef.current = next;
      setStrikesState(next);
      scheduleSave(canvasRef.current, next);
    },
    [scheduleSave],
  );

  const clearCanvas = useCallback(() => {
    const next = emptyCanvas();
    canvasRef.current = next;
    setCanvasState(next);
    scheduleSave(next, strikesRef.current);
  }, [scheduleSave]);

  const clearStrikes = useCallback(() => {
    const next = emptyStrikes();
    strikesRef.current = next;
    setStrikesState(next);
    scheduleSave(canvasRef.current, next);
  }, [scheduleSave]);

  const flush = useCallback(async () => {
    if (!currentQuestion) return;
    const pending: PendingSave = { ...currentQuestion, canvas: canvasRef.current, strikes: strikesRef.current };
    const timer = saveTimers.current.get(pending.key);
    if (timer) {
      clearTimeout(timer);
      saveTimers.current.delete(pending.key);
    }
    localStorage.setItem(pending.key, JSON.stringify(payloadFor(pending.canvas, pending.strikes)));
    await flushPayload(pending);
  }, [currentQuestion, flushPayload]);

  useEffect(() => {
    const timers = saveTimers.current;
    return () => {
      timers.forEach((timer) => clearTimeout(timer));
      timers.clear();
    };
  }, []);

  return {
    canvas,
    strikes,
    loading,
    saving,
    saveError,
    updateCanvas,
    setCanvas,
    toggleStrike,
    clearCanvas,
    clearStrikes,
    flush,
  };
}

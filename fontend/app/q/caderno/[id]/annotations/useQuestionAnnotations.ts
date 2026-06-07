"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { fetchAnnotations, saveAnnotations } from "./api";
import type { CanvasState, StrikeTarget, StrikesState } from "./types";
import { emptyCanvas, emptyStrikes } from "./types";

function keyFor(cadernoId: number, questaoId: number) {
  return `studia:q:${cadernoId}:${questaoId}:annotations`;
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
  const [canvas, setCanvas] = useState<CanvasState>(emptyCanvas);
  const [strikes, setStrikes] = useState<StrikesState>(emptyStrikes);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loadedKey = useMemo(() => (cadernoId && questaoId ? keyFor(cadernoId, questaoId) : null), [cadernoId, questaoId]);

  useEffect(() => {
    if (!cadernoId || !questaoId) return;
    let cancelled = false;
    setLoading(true);
    setSaveError(null);

    const localRaw = localStorage.getItem(keyFor(cadernoId, questaoId));
    if (localRaw) {
      try {
        const local = JSON.parse(localRaw);
        setCanvas(local.canvas_json || emptyCanvas());
        setStrikes(local.strikes_json || emptyStrikes());
      } catch {
        localStorage.removeItem(keyFor(cadernoId, questaoId));
      }
    } else {
      setCanvas(emptyCanvas());
      setStrikes(emptyStrikes());
    }

    fetchAnnotations(cadernoId, questaoId)
      .then((data) => {
        if (cancelled) return;
        setCanvas(data.canvas_json || emptyCanvas());
        setStrikes(data.strikes_json || emptyStrikes());
        localStorage.removeItem(keyFor(cadernoId, questaoId));
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
  }, [cadernoId, questaoId]);

  const flush = useCallback(
    async (nextCanvas: CanvasState, nextStrikes: StrikesState) => {
      if (!cadernoId || !questaoId) return;
      setSaving(true);
      setSaveError(null);
      try {
        await saveAnnotations(cadernoId, questaoId, nextCanvas, nextStrikes);
        localStorage.removeItem(keyFor(cadernoId, questaoId));
      } catch (error) {
        localStorage.setItem(keyFor(cadernoId, questaoId), JSON.stringify({ canvas_json: nextCanvas, strikes_json: nextStrikes }));
        setSaveError(error instanceof Error ? error.message : "Falha ao salvar anotacoes");
      } finally {
        setSaving(false);
      }
    },
    [cadernoId, questaoId],
  );

  const scheduleSave = useCallback(
    (nextCanvas: CanvasState, nextStrikes: StrikesState) => {
      if (!loadedKey) return;
      if (saveTimer.current) clearTimeout(saveTimer.current);
      saveTimer.current = setTimeout(() => {
        void flush(nextCanvas, nextStrikes);
      }, 700);
    },
    [flush, loadedKey],
  );

  const updateCanvas = useCallback(
    (updater: (current: CanvasState) => CanvasState) => {
      setCanvas((current) => {
        const next = updater(current);
        scheduleSave(next, strikes);
        return next;
      });
    },
    [scheduleSave, strikes],
  );

  const toggleStrike = useCallback(
    (target: StrikeTarget) => {
      setStrikes((current) => {
        const nextTargets = hasTarget(current.targets, target)
          ? current.targets.filter((item) => !hasTarget([item], target))
          : [...current.targets, target];
        const next = { version: 1 as const, targets: nextTargets };
        scheduleSave(canvas, next);
        return next;
      });
    },
    [canvas, scheduleSave],
  );

  const clearCanvas = useCallback(() => {
    const next = emptyCanvas();
    setCanvas(next);
    scheduleSave(next, strikes);
  }, [scheduleSave, strikes]);

  useEffect(() => {
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
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
    flush: () => flush(canvas, strikes),
  };
}

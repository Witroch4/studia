"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import { Skeleton } from "../components/ds/Skeleton";

type CatalogModel = {
  value: string;
  label: string;
  provider: string;
  description?: string | null;
  pricing?: string | null;
  capabilities?: { vision?: boolean } | null;
};

type Catalog = { source: "central" | "local_fallback"; models: CatalogModel[] };

type LlmSettings = {
  calculadora_reconhecimento: string;
  processamento_pdf: string;
  chat_aula: string;
};

type SettingsField = keyof LlmSettings;

/** Deriva o id Gemini upstream do alias canônico (sufixo após o prefixo WitDev). */
function geminiIdFromAlias(alias: string): string {
  const parts = alias.split("/");
  return parts[parts.length - 1];
}

/** Recursos que continuam na genai SDK (Batch 50% off) → só Gemini, id upstream. */
function geminiOptions(catalog: Catalog): CatalogModel[] {
  const seen = new Set<string>();
  const options: CatalogModel[] = [];
  for (const m of catalog.models) {
    if ((m.provider || "").toLowerCase() !== "gemini") continue;
    const gid = geminiIdFromAlias(m.value);
    if (seen.has(gid)) continue;
    seen.add(gid);
    options.push({ ...m, value: gid });
  }
  return options;
}

/** Calculadora: catálogo completo; se capabilities veio, só modelos com visão. */
function visionOptions(catalog: Catalog): CatalogModel[] {
  const hasCapabilities = catalog.models.some((m) => m.capabilities != null);
  if (!hasCapabilities) return catalog.models;
  return catalog.models.filter((m) => m.capabilities?.vision);
}

function ModelRow({
  title,
  detail,
  field,
  options,
  settings,
}: {
  title: string;
  detail: string;
  field: SettingsField;
  options: CatalogModel[];
  settings: LlmSettings;
}) {
  const queryClient = useQueryClient();
  const saved = settings[field];
  const [selected, setSelected] = useState(saved);
  const [feedback, setFeedback] = useState<"ok" | "erro" | null>(null);

  // Settings recarregados (ex.: outro admin salvou) → re-sincroniza o dropdown.
  useEffect(() => {
    setSelected(saved);
  }, [saved]);

  const mutation = useMutation({
    mutationFn: (value: string) =>
      apiJson<LlmSettings>("/api/admin/llm/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ [field]: value }),
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(qk.adminLlmSettings(), data);
      setFeedback("ok");
    },
    onError: () => setFeedback("erro"),
  });

  useEffect(() => {
    if (!feedback) return;
    const timer = setTimeout(() => setFeedback(null), 2500);
    return () => clearTimeout(timer);
  }, [feedback]);

  // Valor salvo pode não estar na lista atual (catálogo mudou) — mantém visível.
  const hasSelected = options.some((m) => m.value === selected);
  const dirty = selected !== saved;

  return (
    <div className="flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-center sm:gap-4">
      <div className="min-w-0 sm:w-64 sm:shrink-0">
        <p className="text-sm font-medium text-fg-strong">{title}</p>
        <p className="text-xs text-fg-faint">{detail}</p>
      </div>
      <select
        value={selected}
        onChange={(event) => setSelected(event.target.value)}
        className="h-9 min-w-0 flex-1 rounded border border-border bg-page px-2 text-sm text-fg outline-none transition focus:border-primary"
        aria-label={`Modelo para ${title}`}
      >
        {!hasSelected && selected && (
          <option value={selected}>{selected} (fora do catálogo atual)</option>
        )}
        {options.map((m) => (
          <option key={m.value} value={m.value}>
            {m.label}
            {m.pricing ? ` — ${m.pricing}` : ""}
          </option>
        ))}
      </select>
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={() => mutation.mutate(selected)}
          disabled={!dirty || mutation.isPending}
          className="rounded border border-primary/40 bg-primary/10 px-3 py-1.5 text-xs font-semibold text-primary transition hover:bg-primary/20 disabled:opacity-40"
        >
          {mutation.isPending ? "Salvando…" : "Salvar"}
        </button>
        {/* Área reservada p/ feedback — não desloca o layout */}
        <span
          className={`w-14 text-xs ${feedback === "ok" ? "text-accent-success" : "text-accent-error"}`}
          aria-live="polite"
        >
          {feedback === "ok" ? "Salvo ✓" : feedback === "erro" ? "Falhou" : ""}
        </span>
      </div>
    </div>
  );
}

export function ModelosIaSection() {
  const { data: catalog, isPending: catalogPending } = useQuery<Catalog>({
    queryKey: qk.adminLlmModels(),
    queryFn: () => apiJson<Catalog>("/api/admin/llm/models"),
    staleTime: 60_000,
  });

  const { data: settings, isPending: settingsPending } = useQuery<LlmSettings>({
    queryKey: qk.adminLlmSettings(),
    queryFn: () => apiJson<LlmSettings>("/api/admin/llm/settings"),
  });

  const calcOptions = useMemo(() => (catalog ? visionOptions(catalog) : []), [catalog]);
  const geminiOnly = useMemo(() => (catalog ? geminiOptions(catalog) : []), [catalog]);

  const loading = catalogPending || settingsPending;

  return (
    <div className="mb-8 overflow-hidden rounded-xl border border-border bg-surface">
      <div className="flex items-center justify-between border-b border-border px-5 py-3">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-fg-strong">
          <span className="material-symbols-outlined text-[18px] text-primary">smart_toy</span>
          Modelos de IA
        </h2>
        {catalog?.source === "local_fallback" && (
          <span className="rounded-full bg-warning/15 px-2 py-0.5 text-[10px] font-medium text-warning">
            Catálogo central indisponível — usando lista local
          </span>
        )}
      </div>

      {loading || !catalog || !settings ? (
        // Skeleton no formato final: 3 linhas de recurso (regra "não pula na tela")
        <div className="divide-y divide-border">
          {[1, 2, 3].map((i) => (
            <div key={i} className="flex items-center gap-4 px-5 py-3">
              <div className="w-64 shrink-0 space-y-1.5">
                <Skeleton className="h-4 w-48" />
                <Skeleton className="h-3 w-36" />
              </div>
              <Skeleton className="h-9 flex-1" />
              <Skeleton className="h-8 w-24 shrink-0" />
            </div>
          ))}
        </div>
      ) : (
        <div className="divide-y divide-border">
          <ModelRow
            title="Calculadora · reconhecimento de desenho"
            detail="Visão multimodal via proxy (alias canônico)"
            field="calculadora_reconhecimento"
            options={calcOptions}
            settings={settings}
          />
          <ModelRow
            title="Processamento de PDF · Batch"
            detail="genai SDK (Batch 50% off) — só Gemini"
            field="processamento_pdf"
            options={geminiOnly}
            settings={settings}
          />
          <ModelRow
            title="Chat de aula"
            detail="genai SDK via passthrough — só Gemini"
            field="chat_aula"
            options={geminiOnly}
            settings={settings}
          />
        </div>
      )}
    </div>
  );
}

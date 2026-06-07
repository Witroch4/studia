"use client";

import { useEffect } from "react";

/**
 * useHotkeys — registra teclas globais (event.key insensível a maiúsculas).
 *
 * Mapeamento extraído do TC ([tec-click-when-key]) via MCP DevTools, 2026-06-06.
 * Documentação completa em /docs/witdev-tec-master-ux.md §2.3.
 *
 * Exemplo:
 *   useHotkeys({
 *     ArrowLeft: () => prev(),
 *     ArrowRight: () => next(),
 *     l: () => aleatoria(),
 *     m: () => favoritar(),
 *   });
 *
 * Ignora teclas quando o foco está em input/textarea/contenteditable.
 */
export function useHotkeys(
  map: Record<string, (e: KeyboardEvent) => void>,
  options: { enabled?: boolean } = {},
) {
  const enabled = options.enabled ?? true;

  useEffect(() => {
    if (!enabled) return;

    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement | null)?.tagName?.toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select") return;
      if ((e.target as HTMLElement | null)?.isContentEditable) return;

      // chave: combina Ctrl/Shift quando necessário
      const ctrl = e.ctrlKey || e.metaKey;
      const key = e.key.length === 1 ? e.key.toLowerCase() : e.key;
      const combo = ctrl ? `Ctrl+${key}` : key;

      const cb = map[combo] ?? map[key];
      if (cb) {
        e.preventDefault();
        cb(e);
      }
    };

    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [map, enabled]);
}

// Mapa oficial dos atalhos TC adotados (referência canônica)
export const ATALHOS_TC = {
  // Navegação
  ArrowLeft: { label: "Anterior", group: "nav" },
  ArrowRight: { label: "Próxima", group: "nav" },
  l: { label: "Aleatória não resolvida", group: "nav" },
  n: { label: "Próxima não resolvida", group: "nav" },
  z: { label: "Tópico anterior", group: "nav" },
  x: { label: "Tópico seguinte", group: "nav" },
  "Ctrl+z": { label: "Desfaz última navegação", group: "nav" },
  v: { label: "Próxima favorita do caderno", group: "nav" },
  u: { label: "Próxima anotada do caderno", group: "nav" },
  p: { label: "Ir para… (modal por número)", group: "nav" },
  // Ações na questão
  m: { label: "Favoritar (com confirmação)", group: "acao" },
  j: { label: "Favoritar direto", group: "acao" },
  w: { label: "Alterar anotação", group: "acao" },
  o: { label: "Comentário da questão", group: "acao" },
  f: { label: "Fórum de discussão", group: "acao" },
  h: { label: "Desempenho nesta questão", group: "acao" },
  i: { label: "Detalhes", group: "acao" },
  y: { label: "Toggle texto associado", group: "acao" },
  q: { label: "Adicionar a caderno", group: "acao" },
  // UI
  "+": { label: "Aumentar fonte", group: "ui" },
  "=": { label: "Aumentar fonte (alias)", group: "ui" },
  "-": { label: "Reduzir fonte", group: "ui" },
  "0": { label: "Fonte padrão", group: "ui" },
  k: { label: "Alternar modo leitura", group: "ui" },
  ".": { label: "Pausar/retomar relógio", group: "ui" },
} as const;

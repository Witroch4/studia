import type { CSSProperties } from "react";

/**
 * Skeleton — bloco placeholder (shimmer) que reserva o espaço do conteúdo final
 * enquanto os dados carregam, para que nada "pule" na tela quando chegam.
 * Ver a regra rígida "DADOS NÃO PODEM PULAR NA TELA" no CLAUDE.md.
 *
 * Use para carga rápida de banco (lista de comentários, cards, linhas). Para
 * operações lentas/incertas (import sob demanda via scraper) use <BrandLoader>.
 *
 * Cor via token `--color-fg` com 10% de opacidade → adapta a tema claro/escuro.
 * Server-safe (sem hooks).
 */
export interface SkeletonProps {
  className?: string;
  style?: CSSProperties;
}

export function Skeleton({ className = "", style }: SkeletonProps) {
  return (
    <div
      aria-hidden
      className={`animate-pulse rounded-md bg-fg/10 ${className}`}
      style={style}
    />
  );
}

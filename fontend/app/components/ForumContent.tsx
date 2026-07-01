"use client";

import type { CSSProperties } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import { API_BASE } from "@/lib/api";
import { normalizeForumMath } from "./forumMath";
import { forumRehypePlugins, forumRemarkPlugins } from "./forumMarkdown";

/**
 * Renderiza conteúdo de comentário do fórum (gerado por usuário).
 *
 * Diferente do MarkdownRenderer (só para conteúdo CONFIÁVEL), aqui o pipeline
 * é SANITIZADO contra XSS:
 *  - rehype-raw converte o HTML do usuário em nós e o rehype-sanitize (logo em
 *    seguida, ANTES do rehype-katex) remove tudo fora do schema; só então o
 *    KaTeX renderiza as fórmulas a partir dos nós math.
 *  - <span data-cor|data-fundo|data-tam> é a formatação do editor; os valores
 *    são validados em estiloFormatacao antes de virar style.
 *  - <img> só é aceito se apontar para o endpoint de imagem do fórum.
 */
/**
 * Permite src APENAS se for o endpoint de imagem do fórum:
 *  - relativo:  /api/q/forum/imagem/...
 *  - absoluto:  ${API_BASE}/api/q/forum/imagem/... (inserido por uploadImagemForum)
 * URLs externas arbitrárias são bloqueadas para evitar rastreamento/exfiltração de IP.
 */
function imagemPermitida(src: string | undefined): boolean {
  if (!src) return false;
  if (src.startsWith("/api/q/forum/imagem/")) return true;
  if (src.startsWith(`${API_BASE}/api/q/forum/imagem/`)) return true;
  return false;
}

/**
 * Formatação de texto do editor do fórum via <span data-cor/data-fundo/data-tam>.
 * O sanitize deixa passar só esses data-attrs; os VALORES são validados aqui
 * (hex de cor e px limitado) antes de virarem style — nunca CSS cru do usuário.
 */
const HEX_COR = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;
const TAM_MIN = 10;
const TAM_MAX = 40;

function estiloFormatacao(props: Record<string, unknown>): CSSProperties | null {
  const style: CSSProperties = {};
  const cor = props["data-cor"];
  const fundo = props["data-fundo"];
  const tam = Number(props["data-tam"]);
  if (typeof cor === "string" && HEX_COR.test(cor)) style.color = cor;
  if (typeof fundo === "string" && HEX_COR.test(fundo)) {
    style.backgroundColor = fundo;
    style.borderRadius = 3;
    style.padding = "0 3px";
  }
  if (Number.isFinite(tam) && tam >= TAM_MIN && tam <= TAM_MAX) {
    style.fontSize = `${Math.round(tam)}px`;
    style.lineHeight = 1.4;
  }
  return Object.keys(style).length ? style : null;
}

const components: Components = {
  h1: ({ children }) => <h3 className="text-base font-bold text-fg-strong mt-3 mb-1.5">{children}</h3>,
  h2: ({ children }) => <h3 className="text-base font-bold text-fg-strong mt-3 mb-1.5">{children}</h3>,
  h3: ({ children }) => <h4 className="text-sm font-bold text-fg-strong mt-2 mb-1">{children}</h4>,
  p: ({ children }) => <p className="text-fg text-sm leading-relaxed mb-2">{children}</p>,
  strong: ({ children }) => <strong className="text-fg-strong font-semibold">{children}</strong>,
  ul: ({ children }) => <ul className="list-disc pl-5 space-y-1 mb-2 marker:text-primary/50">{children}</ul>,
  ol: ({ children }) => <ol className="list-decimal pl-5 space-y-1 mb-2">{children}</ol>,
  li: ({ children }) => <li className="text-fg text-sm leading-relaxed">{children}</li>,
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline">
      {children}
    </a>
  ),
  code: ({ children }) => (
    <code className="bg-black/30 px-1.5 py-0.5 rounded text-primary font-mono text-xs">{children}</code>
  ),
  blockquote: ({ children }) => (
    <blockquote className="border-l-4 border-primary/40 pl-3 my-2 text-fg-muted italic">{children}</blockquote>
  ),
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-border bg-surface/40">
      <table className="w-full min-w-[640px] border-collapse text-left text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-white/5 text-fg-strong">{children}</thead>,
  tbody: ({ children }) => <tbody className="divide-y divide-border/70">{children}</tbody>,
  tr: ({ children }) => <tr className="align-top">{children}</tr>,
  th: ({ children }) => (
    <th className="border-r border-border/70 px-3 py-2 font-semibold last:border-r-0">{children}</th>
  ),
  td: ({ children }) => (
    <td className="border-r border-border/70 px-3 py-2 leading-relaxed text-fg last:border-r-0">{children}</td>
  ),
  span: ({ node: _node, children, style, ...rest }) => {
    // spans do KaTeX e afins passam intactos; só os data-attrs validados ganham style
    const extra = estiloFormatacao(rest as Record<string, unknown>);
    return (
      <span {...rest} style={extra ? { ...style, ...extra } : style}>
        {children}
      </span>
    );
  },
  img: ({ src, alt }) => {
    const url = typeof src === "string" ? src : "";
    if (!imagemPermitida(url)) {
      return <span className="text-error text-xs">[imagem bloqueada]</span>;
    }
    const full = url.startsWith("http") ? url : `${API_BASE}${url}`;
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={full} alt={alt || ""} className="max-w-full rounded-lg my-2 border border-border" />;
  },
};

interface ForumContentProps {
  content: string;
  className?: string;
}

export default function ForumContent({ content, className = "" }: ForumContentProps) {
  const normalizedContent = normalizeForumMath(content);

  return (
    <div className={`forum-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={forumRemarkPlugins}
        rehypePlugins={forumRehypePlugins}
        components={components}
      >
        {normalizedContent}
      </ReactMarkdown>
    </div>
  );
}

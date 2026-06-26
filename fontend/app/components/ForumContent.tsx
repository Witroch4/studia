"use client";

import ReactMarkdown, { type Components } from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import { API_BASE } from "@/lib/api";

/**
 * Renderiza conteúdo de comentário do fórum (gerado por usuário).
 *
 * Diferente do MarkdownRenderer (que usa rehype-raw e é só para conteúdo
 * CONFIÁVEL), aqui o pipeline é SANITIZADO contra XSS:
 *  - rehype-sanitize roda ANTES do rehype-katex; assim o HTML do usuário é
 *    higienizado e só então o KaTeX renderiza as fórmulas a partir dos nós math.
 *  - <img> só é aceito se apontar para o endpoint de imagem do fórum.
 */
const schema = {
  ...defaultSchema,
  // span e div já estão em defaultSchema.tagNames; sem override necessário
  attributes: {
    ...defaultSchema.attributes,
    span: [...(defaultSchema.attributes?.span ?? []), ["className", "math", "math-inline", "math-display"]],
    div: [...(defaultSchema.attributes?.div ?? []), ["className", "math", "math-display"]],
    img: [...(defaultSchema.attributes?.img ?? []), "src", "alt", "title"],
  },
};

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
  return (
    <div className={`forum-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[[rehypeSanitize, schema], rehypeKatex]}
        components={components}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

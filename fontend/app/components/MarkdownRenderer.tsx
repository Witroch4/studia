"use client";

import ReactMarkdown from "react-markdown";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import type { Components } from "react-markdown";

/**
 * Pré-processa tags XML customizadas transformando em HTML divs
 * que o rehype-raw vai preservar.
 *
 * Tags suportadas:
 *   <atencao>texto</atencao>  → callout vermelho
 *   <destaque>texto</destaque> → highlight cyan inline
 *   <resumo>texto</resumo>    → box destaque centralizado
 */
function preprocessTags(content: string): string {
  let processed = content;

  // Block-level tags: blank lines around content force the markdown parser
  // to exit HTML-block mode and process math/markdown inside the tag.
  processed = processed.replace(
    /<atencao>([\s\S]*?)<\/atencao>/g,
    '<div data-tag="atencao">\n\n$1\n\n</div>'
  );

  processed = processed.replace(
    /<resumo>([\s\S]*?)<\/resumo>/g,
    '<div data-tag="resumo">\n\n$1\n\n</div>'
  );

  // Inline tag: <span> allows inline markdown processing naturally
  processed = processed.replace(
    /<destaque>([\s\S]*?)<\/destaque>/g,
    '<span data-tag="destaque">$1</span>'
  );

  return processed;
}

const mdComponents: Components = {
  h1: ({ children }) => (
    <h1 className="text-xl font-bold text-fg-strong mb-3 mt-4">{children}</h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-lg font-bold text-fg-strong mb-2 mt-3">{children}</h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-base font-bold text-fg-strong mb-2 mt-3 pb-1 border-b border-primary/15">
      {children}
    </h3>
  ),
  p: ({ children }) => (
    <p className="text-fg text-[0.9rem] leading-relaxed mb-3">{children}</p>
  ),
  strong: ({ children }) => (
    <strong className="text-fg-strong font-semibold">{children}</strong>
  ),
  em: ({ children }) => (
    <em className="text-fg italic">{children}</em>
  ),
  ul: ({ children }) => (
    <ul className="space-y-1.5 pl-4 mb-3">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="space-y-1.5 pl-4 mb-3 list-decimal">{children}</ol>
  ),
  li: ({ children }) => (
    <li className="text-fg text-[0.9rem] leading-relaxed list-disc marker:text-primary/50">
      {children}
    </li>
  ),
  code: ({ children, className }) => {
    if (className) {
      return (
        <code className="block bg-black/30 rounded-xl border border-border-dark p-4 font-mono text-primary text-sm overflow-x-auto mb-3">
          {children}
        </code>
      );
    }
    return (
      <code className="bg-black/30 px-1.5 py-0.5 rounded text-primary font-mono text-sm">
        {children}
      </code>
    );
  },
  div: ({ node, children, ...props }) => {
    const dataTag = (props as Record<string, string>)["data-tag"];

    if (dataTag === "atencao") {
      return (
        <div className="my-3 bg-red-500/8 border-l-3 border-red-500 px-4 py-2.5 rounded-r-lg text-sm text-fg">
          {children}
        </div>
      );
    }

    if (dataTag === "resumo") {
      return (
        <div className="my-3 bg-primary/10 border border-primary/30 p-4 rounded-lg text-primary font-bold text-center text-lg">
          {children}
        </div>
      );
    }

    return <div {...props}>{children}</div>;
  },
  span: ({ node, children, ...props }) => {
    const dataTag = (props as Record<string, string>)["data-tag"];

    if (dataTag === "destaque") {
      return (
        <span className="bg-primary/15 text-primary px-1.5 py-0.5 rounded font-medium">
          {children}
        </span>
      );
    }

    return <span {...props}>{children}</span>;
  },
};

interface MarkdownRendererProps {
  content: string;
  className?: string;
}

export default function MarkdownRenderer({ content, className = "" }: MarkdownRendererProps) {
  const processed = preprocessTags(content);

  return (
    <div className={`markdown-content ${className}`}>
      <ReactMarkdown
        remarkPlugins={[remarkMath]}
        rehypePlugins={[rehypeKatex, rehypeRaw]}
        components={mdComponents}
      >
        {processed}
      </ReactMarkdown>
    </div>
  );
}

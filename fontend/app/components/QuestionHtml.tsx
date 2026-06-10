"use client";

import katex from "katex";
import { useCallback, useEffect, useRef, type HTMLAttributes } from "react";

interface QuestionHtmlProps extends HTMLAttributes<HTMLElement> {
  html: string;
  as?: "div" | "span" | "article";
}

/**
 * Renderiza HTML de questão vindo do TecConcursos. O TC marca fórmulas com
 * <span class="render-latex">...LaTeX cru...</span> e renderiza via MathJax
 * no browser; aqui fazemos o mesmo com o KaTeX já usado nos flashcards.
 */
export default function QuestionHtml({ html, as: Tag = "div", ...props }: QuestionHtmlProps) {
  const ref = useRef<HTMLElement | null>(null);
  const setRef = useCallback((el: HTMLElement | null) => {
    ref.current = el;
  }, []);

  useEffect(() => {
    const spans = ref.current?.querySelectorAll<HTMLElement>("span.render-latex");
    spans?.forEach((el) => {
      if (el.dataset.katexDone) return;
      const tex = el.textContent ?? "";
      try {
        katex.render(tex, el, { throwOnError: false, strict: "ignore" });
      } catch {
        // mantém o LaTeX cru como fallback
      }
      el.dataset.katexDone = "1";
    });
  }, [html]);

  return <Tag {...props} ref={setRef} dangerouslySetInnerHTML={{ __html: html }} />;
}

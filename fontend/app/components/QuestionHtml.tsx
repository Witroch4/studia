"use client";

import katex from "katex";
import { useCallback, useEffect, useMemo, useRef, type HTMLAttributes } from "react";

interface QuestionHtmlProps extends HTMLAttributes<HTMLElement> {
  html: string;
  as?: "div" | "span" | "article";
}

/**
 * Renderiza HTML de questão vindo do TecConcursos. O TC marca fórmulas com
 * <span class="render-latex">...LaTeX cru...</span> e renderiza via MathJax
 * no browser; aqui fazemos o mesmo com o KaTeX já usado nos flashcards.
 *
 * O objeto {__html} é memoizado: objeto novo a cada render faz o React 19
 * reaplicar o innerHTML em todo commit do pai (ex.: tick do timer do
 * caderno), apagando a saída do KaTeX. O efeito roda após cada commit e só
 * processa spans ainda crus, então sobrevive a resets residuais.
 */
export default function QuestionHtml({ html, as: Tag = "div", ...props }: QuestionHtmlProps) {
  const ref = useRef<HTMLElement | null>(null);
  const setRef = useCallback((el: HTMLElement | null) => {
    ref.current = el;
  }, []);

  const htmlObj = useMemo(() => ({ __html: html }), [html]);

  useEffect(() => {
    const spans = ref.current?.querySelectorAll<HTMLElement>(
      "span.render-latex:not([data-katex-done])",
    );
    spans?.forEach((el) => {
      const tex = el.textContent ?? "";
      try {
        katex.render(tex, el, { throwOnError: false, strict: "ignore" });
      } catch {
        // mantém o LaTeX cru como fallback
      }
      el.dataset.katexDone = "1";
    });
  });

  return <Tag {...props} ref={setRef} dangerouslySetInnerHTML={htmlObj} />;
}

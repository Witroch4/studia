"""Conversão HTML → Markdown preservando o LaTeX do TecConcursos.

O TC marca fórmulas com <span class="render-latex">...</span> e as renderiza
no browser via MathJax. Passar esse HTML direto pelo markdownify mutila o
LaTeX (\\omega vira \\\\omega, x_1 vira x\\_1); aqui os spans são extraídos
antes da conversão e restaurados como ``$...$`` no markdown final.
"""

from __future__ import annotations

from app.observability import get_logger

log = get_logger(__name__)

_TOKEN = "@@LATEX{}@@"


def html_to_md(html: str | None) -> str | None:
    if not html:
        return None
    try:
        from bs4 import BeautifulSoup
        from markdownify import markdownify

        soup = BeautifulSoup(html, "html.parser")
        formulas: list[str] = []
        for span in soup.select("span.render-latex"):
            formulas.append(span.get_text().strip())
            span.replace_with(_TOKEN.format(len(formulas) - 1))

        md = markdownify(str(soup), heading_style="ATX").strip()
        for i, tex in enumerate(formulas):
            md = md.replace(_TOKEN.format(i), f"${tex}$")
        return md
    except Exception as e:  # noqa: BLE001
        log.warning("md.fallback", err=str(e))
        return html

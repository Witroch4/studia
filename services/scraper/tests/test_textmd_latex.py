"""html_to_md deve preservar o LaTeX dos spans .render-latex do TC."""

from app.textmd import html_to_md


def test_render_latex_vira_dolar():
    html = (
        '<p style="text-align:justify">&nbsp;<span class="render-latex" contenteditable="false">'
        r"\omega^2 \rho \begin{bmatrix} x_1 \\ 0 \\ 0 \end{bmatrix}"
        "</span></p>"
    )
    md = html_to_md(html)
    assert r"$\omega^2 \rho \begin{bmatrix} x_1 \\ 0 \\ 0 \end{bmatrix}$" in md
    assert r"\\omega" not in md
    assert r"x\_1" not in md


def test_multiplos_spans_preservam_ordem():
    html = (
        '<p><span class="render-latex">a_1</span> e '
        '<span class="render-latex">b^2</span></p>'
    )
    md = html_to_md(html)
    assert "$a_1$" in md
    assert "$b^2$" in md
    assert md.index("$a_1$") < md.index("$b^2$")


def test_html_sem_latex_segue_normal():
    assert html_to_md("<p><strong>Certo</strong></p>") == "**Certo**"


def test_vazio():
    assert html_to_md(None) is None
    assert html_to_md("") is None

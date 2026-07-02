import assert from "node:assert/strict";
import test from "node:test";

import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";

import { forumRehypePlugins, forumRemarkPlugins } from "./forumMarkdown.ts";

const tableMarkdown = `| Alternativa | Descrição na Questão | Nomenclatura Correta (Elemento) | Função Estrutural / Formato |
| --- | --- | --- | --- |
| **A** | Perfil utilizado verticalmente na composição de painéis de parede. | **Montante** *(Stud)* | É a "coluna" do painel. |
| **B (Correta)** | Perfil utilizado como base e topo... e aberturas. | **Guia** *(Track)* | É o "trilho" horizontal. |`;

function render(md) {
  return renderToStaticMarkup(
    React.createElement(
      ReactMarkdown,
      { remarkPlugins: forumRemarkPlugins, rehypePlugins: forumRehypePlugins },
      md
    )
  );
}

test("REGRESSÃO: fórmula $...$ dentro de HTML do editor novo renderiza KaTeX", () => {
  // trecho real do comentário 15747 de prod (colado do Gemini no editor novo)
  const html = render(
    "<p>A base para resolver essa questão é a famosa equação de Terzaghi:</p>"
    + "<p>$\\sigma' = \\sigma - u$</p>"
    + '<p>Esta é a definição exata de <strong>Tensão Efetiva</strong> ($\\sigma\'$), e não de pressão neutra ($u$).</p>'
  );
  assert.match(html, /class="katex"/);
  assert.doesNotMatch(html, /\$\\sigma/);
  assert.doesNotMatch(html, /\$u\$/);
});

test("math em bloco $$...$$ dentro de HTML renderiza em displayMode", () => {
  const html = render("<p>Veja:</p><p>$$\\frac{a}{b}$$</p>");
  assert.match(html, /katex-display/);
  assert.doesNotMatch(html, /\$\$/);
});

test("cifrão de dinheiro dentro de HTML não vira fórmula", () => {
  const html = render("<p>custa R$ 100 e o total dá R$ 250 na banca</p>");
  assert.doesNotMatch(html, /class="katex"/);
  assert.match(html, /R\$ 100/);
});

test("latex com underscore dentro de HTML não vira itálico", () => {
  const html = render("<p>tensões: $\\sigma_a + \\sigma_b$</p>");
  assert.match(html, /class="katex"/);
  assert.doesNotMatch(html, /<em>/);
});

test("fórmula em markdown puro continua funcionando (sem dupla conversão)", () => {
  const html = render("A energia $E=mc^2$ é **famosa**.");
  assert.match(html, /class="katex"/);
  assert.match(html, /<strong>famosa<\/strong>/);
});

test("HTML emitido pelo editor TipTap renderiza inteiro", () => {
  const html = render(
    '<p><strong>a</strong> <em>b</em></p><blockquote><p>cit</p></blockquote>'
    + '<ul><li>um</li></ul>'
    + '<p><span data-fundo="#eab308"><span data-cor="#ef4444">forte</span></span></p>'
  );
  assert.match(html, /<strong>a<\/strong>/);
  assert.match(html, /<blockquote/);
  assert.match(html, /<li[^>]*>um<\/li>/);
  assert.match(html, /data-fundo="#eab308"/);
  assert.match(html, /data-cor="#ef4444"/);
});

test("style inline salvo pelo editor é descartado no render", () => {
  const html = render('<p><span data-cor="#ef4444" style="color:#ef4444;position:fixed">x</span></p>');
  assert.doesNotMatch(html, /position:fixed/);
  assert.match(html, /data-cor="#ef4444"/);
});

test("span de formatação (data-cor/data-fundo/data-tam) sobrevive à sanitização", () => {
  const html = render(
    'Texto <span data-cor="#ff0000" data-fundo="#1e1e1e" data-tam="20">colorido</span> normal'
  );
  assert.match(html, /data-cor="#ff0000"/);
  assert.match(html, /data-fundo="#1e1e1e"/);
  assert.match(html, /data-tam="20"/);
  assert.match(html, /colorido/);
});

test("sanitização remove atributos e tags perigosos do HTML do usuário", () => {
  const html = render(
    '<span onclick="alert(1)" style="position:fixed" data-cor="#f00">oi</span><script>alert(2)</script>'
  );
  assert.doesNotMatch(html, /onclick/);
  assert.doesNotMatch(html, /position:fixed/);
  assert.doesNotMatch(html, /<script/);
  assert.match(html, /data-cor="#f00"/);
});

test("fórmulas KaTeX continuam funcionando com o pipeline de HTML cru", () => {
  const html = render('Energia: $E=mc^2$ <span data-cor="#0af">fim</span>');
  assert.match(html, /class="katex"/);
  assert.match(html, /data-cor="#0af"/);
});

test("renderiza tabelas Markdown GFM do forum como tabela HTML real", () => {
  const html = renderToStaticMarkup(
    React.createElement(
      ReactMarkdown,
      {
        remarkPlugins: forumRemarkPlugins,
        rehypePlugins: forumRehypePlugins,
      },
      tableMarkdown
    )
  );

  assert.match(html, /<table>/);
  assert.match(html, /<thead>/);
  assert.match(html, /<tbody>/);
  assert.match(html, /<th>Alternativa<\/th>/);
  assert.match(html, /<td><strong>A<\/strong><\/td>/);
  assert.doesNotMatch(html, /^\s*<p>\| Alternativa/m);
});

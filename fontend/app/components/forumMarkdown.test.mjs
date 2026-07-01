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

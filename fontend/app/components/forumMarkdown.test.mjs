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

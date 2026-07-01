import assert from "node:assert/strict";
import test from "node:test";

import {
  escaparHtml, htmlEditorVazio, limparImagensExternas,
  markdownParaHtml, mathHtmlParaDelimitadores, pareceHtml,
} from "./forumEditorHtml.ts";

test("math inline e block voltam a delimitadores $", () => {
  const html = '<p>x: <span data-type="inline-math" data-latex="E=mc^2"></span></p>'
    + '<div data-type="block-math" data-latex="\\frac{a}{b}"></div>';
  const out = mathHtmlParaDelimitadores(html);
  assert.match(out, /\$E=mc\^2\$/);
  assert.match(out, /\$\$\\frac\{a\}\{b\}\$\$/);
  assert.doesNotMatch(out, /data-type/);
});

test("math com atributos em outra ordem e entidades escapadas", () => {
  const html = '<span data-latex="a &lt; b &amp; c" data-type="inline-math"></span>';
  assert.equal(mathHtmlParaDelimitadores(html), "$a < b & c$");
});

test("htmlEditorVazio detecta documento vazio", () => {
  assert.equal(htmlEditorVazio(""), true);
  assert.equal(htmlEditorVazio("<p></p>"), true);
  assert.equal(htmlEditorVazio("<p>  </p>"), true);
  assert.equal(htmlEditorVazio("<p>oi</p>"), false);
  assert.equal(htmlEditorVazio('<p><img src="/api/q/forum/imagem/forum/x.png"></p>'), false);
});

test("pareceHtml distingue HTML novo de markdown legado", () => {
  assert.equal(pareceHtml("<p>oi</p>"), true);
  assert.equal(pareceHtml('<span data-cor="#f00">x</span>'), true);
  assert.equal(pareceHtml("**negrito** e $x$"), false);
  assert.equal(pareceHtml("- item\n- outro"), false);
});

test("markdownParaHtml converte md legado preservando $...$", () => {
  const html = markdownParaHtml("**negrito** e $E=mc^2$\n\n| a | b |\n| - | - |\n| 1 | 2 |");
  assert.match(html, /<strong>negrito<\/strong>/);
  assert.match(html, /\$E=mc\^2\$/);
  assert.match(html, /<table>/);
});

test("markdownParaHtml mantém spans de formatação do formato atual", () => {
  const html = markdownParaHtml('texto <span data-cor="#ef4444">vermelho</span>');
  assert.match(html, /data-cor="#ef4444"/);
});

test("limparImagensExternas remove só as de fora", () => {
  const html = '<p><img src="https://mal.com/x.jpg"><img src="/api/q/forum/imagem/forum/a.png"></p>';
  const out = limparImagensExternas(html);
  assert.doesNotMatch(out, /mal\.com/);
  assert.match(out, /forum\/a\.png/);
});

test("escaparHtml", () => {
  assert.equal(escaparHtml('<a b="c">&'), "&lt;a b=&quot;c&quot;&gt;&amp;");
});

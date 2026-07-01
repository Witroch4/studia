import assert from "node:assert/strict";
import test from "node:test";

import { imagensDoClipboard } from "./forumClipboard.ts";

const png = new File(["fake"], "img.png", { type: "image/png" });
const txt = new File(["x"], "nota.txt", { type: "text/plain" });

function dt({ files = [], items = [] } = {}) {
  return { files, items };
}

test("retorna o blob de imagem do clipboard (caso 'Copiar imagem' do navegador)", () => {
  const out = imagensDoClipboard(dt({ files: [png] }));
  assert.equal(out.length, 1);
  assert.equal(out[0].type, "image/png");
});

test("ignora arquivos que não são imagem suportada", () => {
  const out = imagensDoClipboard(dt({ files: [txt] }));
  assert.equal(out.length, 0);
});

test("cai para items quando files está vazio (variação entre navegadores)", () => {
  const item = { kind: "file", type: "image/jpeg", getAsFile: () => png };
  const out = imagensDoClipboard(dt({ items: [item] }));
  assert.equal(out.length, 1);
});

test("clipboard só com texto/html não retorna nada (segue o fluxo turndown)", () => {
  const item = { kind: "string", type: "text/html", getAsFile: () => null };
  const out = imagensDoClipboard(dt({ items: [item] }));
  assert.equal(out.length, 0);
});

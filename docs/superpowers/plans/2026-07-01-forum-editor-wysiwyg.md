# Editor WYSIWYG do fórum (TipTap) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Substituir o textarea do `CommentEditor` por um editor WYSIWYG TipTap onde imagem, cor, fundo, tamanho e fórmulas aparecem renderizados ao vivo, salvando no formato atual do fórum.

**Architecture:** TipTap v3 (ProseMirror) com três marks customizados que serializam `<span data-cor|data-fundo|data-tam>` (formato já aceito pelo pipeline sanitizado do `ForumContent`, que não muda). Fórmulas viram nós Mathematics no editor e voltam a `$...$` ao salvar. Upload de imagem reusa `forumClipboard.ts` + `uploadImagemForum` com preview instantâneo via `URL.createObjectURL`.

**Tech Stack:** Next.js 16, React 19, TipTap v3 (`@tiptap/react`, `@tiptap/starter-kit`, `@tiptap/extension-image`, `@tiptap/extension-mathematics`, `@tiptap/extensions`), unified (remark-parse/remark-gfm/remark-rehype/rehype-stringify), KaTeX (já instalado), node --test, Playwright MCP.

## Global Constraints

- Todo commit nasce em worktree (`.claude/worktrees/<nome>`); merge na `main` via `git merge` a partir do checkout principal; **nunca** `git switch` no checkout principal.
- UI em Português BR; **proibido** "TC"/"tec" em texto visível de UI.
- Formato de armazenamento (`texto_md`): HTML simples + `<span data-cor|data-fundo|data-tam>` + `$...$`/`$$...$$` para fórmulas. Sem migração de banco.
- `ForumContent` continua a única fronteira de sanitização/validação para leitores. O editor pode emitir `style` inline no seu próprio DOM, mas **somente** com valores validados (hex `#rgb|#rrggbb`; tam 10–40 int).
- API pública do `CommentEditor` inalterada: `{ onSubmit, onCancel?, submitting?, valorInicial?, autoFocus?, placeholder? }`.
- Testes unit: `node --test app/components/**/*.test.mjs` (Node 24, strip types). Lint: `pnpm lint`. Typecheck: `pnpm exec tsc --noEmit`.
- Subagentes (se usados) rodam com `model: sonnet`.
- Sem estado-vazio piscando: editor reserva `min-height` (regra "dados não pulam").

---

### Task 1: Worktree, dependências e commit do spec

**Files:**
- Modify: `fontend/package.json` (deps novas)
- Commit: `docs/superpowers/specs/2026-07-01-forum-editor-wysiwyg-design.md` (já existe no checkout principal, untracked)

**Interfaces:**
- Produces: worktree `.claude/worktrees/forum-editor-wysiwyg` com deps instaladas; spec versionado.

- [ ] **Step 1: Criar worktree** com a ferramenta EnterWorktree (`name: forum-editor-wysiwyg`). Copiar o spec para dentro do worktree (mesmo caminho relativo `docs/superpowers/specs/...`).

- [ ] **Step 2: Instalar dependências**

```bash
cd fontend
pnpm add @tiptap/react @tiptap/core @tiptap/pm @tiptap/starter-kit @tiptap/extension-image @tiptap/extension-mathematics @tiptap/extensions unified remark-parse remark-rehype rehype-stringify
```

Esperado: instala sem erro de peer deps. Verificar: `node -e "require.resolve('@tiptap/extensions')"` — se o pacote `@tiptap/extensions` não existir/na versão instalada não exportar `Placeholder`, usar `pnpm add @tiptap/extension-placeholder` e importar de lá (ajustar import na Task 4).

- [ ] **Step 3: Sanity de versão** — `pnpm ls @tiptap/react` deve mostrar 3.x. `katex` já deve estar em dependencies (conferir com `grep katex package.json`).

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-07-01-forum-editor-wysiwyg-design.md fontend/package.json fontend/pnpm-lock.yaml
git commit -m "chore(forum): spec do editor WYSIWYG + deps TipTap v3"
```

---

### Task 2: Helpers puros de HTML do editor (TDD)

**Files:**
- Create: `fontend/app/components/editor/forumEditorHtml.ts`
- Test: `fontend/app/components/editor/forumEditorHtml.test.mjs`

**Interfaces:**
- Produces (usado na Task 4):
  - `mathHtmlParaDelimitadores(html: string): string` — spans/divs `data-type="inline-math"|"block-math"` → `$latex$` / `$$latex$$` (com unescape de entidades no `data-latex`).
  - `htmlEditorVazio(html: string): boolean` — `""`, `<p></p>`, whitespace → `true`.
  - `pareceHtml(texto: string): boolean` — heurística p/ distinguir HTML novo de markdown legado.
  - `markdownParaHtml(md: string): string` — conversão SÍNCRONA (unified `.processSync`) preservando `$...$` literal (sem remark-math).
  - `limparImagensExternas(html: string): string` — remove `<img>` cujo src não é `/api/q/forum/imagem/` (relativo ou com API_BASE).
  - `escaparHtml(texto: string): string` — fallback de carga.

- [ ] **Step 1: Escrever os testes que falham**

```js
// fontend/app/components/editor/forumEditorHtml.test.mjs
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
```

- [ ] **Step 2: Rodar e ver falhar** — `node --test app/components/editor/forumEditorHtml.test.mjs` → FAIL (módulo não existe).

- [ ] **Step 3: Implementar**

```ts
// fontend/app/components/editor/forumEditorHtml.ts
// Helpers PUROS (sem DOM) do editor WYSIWYG do fórum — testáveis em node.
import rehypeStringify from "rehype-stringify";
import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import remarkRehype from "remark-rehype";
import { unified } from "unified";

const ENTIDADES: Record<string, string> = {
  "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'", "&#x27;": "'",
};

function desescapar(valor: string): string {
  return valor.replace(/&(?:amp|lt|gt|quot|#39|#x27);/g, (e) => ENTIDADES[e] ?? e);
}

export function escaparHtml(texto: string): string {
  return texto.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function extrairLatex(tag: string): string | null {
  const m = tag.match(/data-latex="([^"]*)"/);
  return m ? desescapar(m[1]) : null;
}

/** Nós Mathematics do TipTap → delimitadores $ (formato dos comentários antigos). */
export function mathHtmlParaDelimitadores(html: string): string {
  return html
    .replace(/<(span|div)\b[^>]*data-type="block-math"[^>]*>[\s\S]*?<\/\1>/g, (tag) => {
      const l = extrairLatex(tag);
      return l === null ? tag : `$$${l}$$`;
    })
    .replace(/<(span|div)\b[^>]*data-type="inline-math"[^>]*>[\s\S]*?<\/\1>/g, (tag) => {
      const l = extrairLatex(tag);
      return l === null ? tag : `$${l}$`;
    });
}

/** True quando o getHTML() do editor é um documento sem conteúdo real. */
export function htmlEditorVazio(html: string): boolean {
  const semTags = html.replace(/<br\s*\/?>/g, "").replace(/<\/?p>/g, "").trim();
  if (!semTags) return true;
  return !/<img|[^\s<>]/.test(semTags) && !/<img/.test(html);
}

const TAGS_BLOCO = /<(p|div|span|ul|ol|li|blockquote|h[1-6]|img|table|pre|strong|em)\b/i;

/** Heurística: conteúdo salvo pelo editor novo é HTML; legado é markdown. */
export function pareceHtml(texto: string): boolean {
  return TAGS_BLOCO.test(texto);
}

const conversorMd = unified()
  .use(remarkParse)
  .use(remarkGfm)
  // SEM remark-math: os $...$ ficam literais para o migrateMathStrings do editor
  .use(remarkRehype, { allowDangerousHtml: true })
  .use(rehypeStringify, { allowDangerousHtml: true });

/** Markdown legado → HTML para carregar no editor. Síncrono (processSync). */
export function markdownParaHtml(md: string): string {
  return String(conversorMd.processSync(md));
}

const IMG_PERMITIDA = /\/api\/q\/forum\/imagem\//;

/** Remove <img> externas de HTML colado — nunca entra conteúdo que o render bloquearia. */
export function limparImagensExternas(html: string): string {
  return html.replace(/<img\b[^>]*>/gi, (tag) => {
    const src = tag.match(/src="([^"]*)"/i)?.[1] ?? "";
    return IMG_PERMITIDA.test(src) ? tag : "";
  });
}
```

Nota: se `htmlEditorVazio` acima se mostrar frágil nos testes, simplificar para: remove todas as tags exceto `img`, e retorna `true` se não sobra nem texto nem `<img`. O teste é o contrato.

- [ ] **Step 4: Rodar até passar** — `node --test app/components/editor/forumEditorHtml.test.mjs` → 8 pass.

- [ ] **Step 5: Commit** — `git add fontend/app/components/editor/ && git commit -m "feat(forum): helpers puros do editor WYSIWYG (math↔$, legado md→html, strip img externa)"`

---

### Task 3: Marks customizados data-cor / data-fundo / data-tam

**Files:**
- Create: `fontend/app/components/editor/forumEditorMarks.ts`

**Interfaces:**
- Consumes: nada (só `@tiptap/core`).
- Produces (usado na Task 4): extensões `CorMark`, `FundoMark`, `TamMark` com comandos
  `setCor(cor: string)` / `unsetCor()`, `setFundo(cor: string)` / `unsetFundo()`,
  `setTam(px: number)` / `unsetTam()`; serialização `<span data-cor="#hex" style="color:#hex">…` (style só com valor validado).

- [ ] **Step 1: Implementar (sem teste unit — coberto por tsc + Playwright na Task 6)**

```ts
// fontend/app/components/editor/forumEditorMarks.ts
// Marks de formatação do fórum. Serializam <span data-*> (formato do render
// sanitizado) e TAMBÉM style inline VALIDADO para o texto aparecer formatado
// dentro do próprio editor. O style é descartado pelo sanitize no render.
import { Mark, mergeAttributes } from "@tiptap/core";

const HEX = /^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$/;

declare module "@tiptap/core" {
  interface Commands<ReturnType> {
    forumFormat: {
      setCor: (cor: string) => ReturnType;
      unsetCor: () => ReturnType;
      setFundo: (cor: string) => ReturnType;
      unsetFundo: () => ReturnType;
      setTam: (px: number) => ReturnType;
      unsetTam: () => ReturnType;
    };
  }
}

export const CorMark = Mark.create({
  name: "cor",
  addAttributes() {
    return {
      cor: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-cor"),
        renderHTML: (attrs) => {
          const cor = typeof attrs.cor === "string" && HEX.test(attrs.cor) ? attrs.cor : null;
          return cor ? { "data-cor": cor, style: `color: ${cor}` } : {};
        },
      },
    };
  },
  parseHTML() {
    return [{ tag: "span[data-cor]" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes(HTMLAttributes), 0];
  },
  addCommands() {
    return {
      setCor: (cor) => ({ commands }) => commands.setMark(this.name, { cor }),
      unsetCor: () => ({ commands }) => commands.unsetMark(this.name),
    };
  },
});

export const FundoMark = Mark.create({
  name: "fundo",
  addAttributes() {
    return {
      fundo: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-fundo"),
        renderHTML: (attrs) => {
          const cor = typeof attrs.fundo === "string" && HEX.test(attrs.fundo) ? attrs.fundo : null;
          return cor
            ? { "data-fundo": cor, style: `background-color: ${cor}; border-radius: 3px; padding: 0 3px` }
            : {};
        },
      },
    };
  },
  parseHTML() {
    return [{ tag: "span[data-fundo]" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes(HTMLAttributes), 0];
  },
  addCommands() {
    return {
      setFundo: (cor) => ({ commands }) => commands.setMark(this.name, { fundo: cor }),
      unsetFundo: () => ({ commands }) => commands.unsetMark(this.name),
    };
  },
});

export const TamMark = Mark.create({
  name: "tam",
  addAttributes() {
    return {
      tam: {
        default: null,
        parseHTML: (el) => el.getAttribute("data-tam"),
        renderHTML: (attrs) => {
          const px = Math.round(Number(attrs.tam));
          return Number.isFinite(px) && px >= 10 && px <= 40
            ? { "data-tam": String(px), style: `font-size: ${px}px; line-height: 1.4` }
            : {};
        },
      },
    };
  },
  parseHTML() {
    return [{ tag: "span[data-tam]" }];
  },
  renderHTML({ HTMLAttributes }) {
    return ["span", mergeAttributes(HTMLAttributes), 0];
  },
  addCommands() {
    return {
      setTam: (px) => ({ commands }) => commands.setMark(this.name, { tam: String(px) }),
      unsetTam: () => ({ commands }) => commands.unsetMark(this.name),
    };
  },
});
```

- [ ] **Step 2: Typecheck** — `pnpm exec tsc --noEmit` → sem erros.

- [ ] **Step 3: Commit** — `git add fontend/app/components/editor/forumEditorMarks.ts && git commit -m "feat(forum): marks TipTap data-cor/data-fundo/data-tam com style validado no editor"`

---

### Task 4: CommentEditor WYSIWYG + estilos

**Files:**
- Rewrite: `fontend/app/q/caderno/[id]/components/CommentEditor.tsx`
- Modify: `fontend/app/globals.css` (bloco `.forum-editor .tiptap`)

**Interfaces:**
- Consumes: Task 2 (`mathHtmlParaDelimitadores`, `htmlEditorVazio`, `pareceHtml`, `markdownParaHtml`, `limparImagensExternas`, `escaparHtml`), Task 3 (marks + comandos), `imagensDoClipboard` (existente), `uploadImagemForum` (existente), `normalizeForumMath` (existente).
- Produces: mesmo componente público `CommentEditor` (props inalteradas). Remove o painel "Pré-visualização" e o turndown.

- [ ] **Step 1: Reescrever o componente**

```tsx
// fontend/app/q/caderno/[id]/components/CommentEditor.tsx
"use client";

import { Mathematics, migrateMathStrings } from "@tiptap/extension-mathematics";
import Image from "@tiptap/extension-image";
import { Placeholder } from "@tiptap/extensions";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useState } from "react";
import { imagensDoClipboard } from "../../../../components/forumClipboard";
import {
  escaparHtml, htmlEditorVazio, limparImagensExternas,
  markdownParaHtml, mathHtmlParaDelimitadores, pareceHtml,
} from "../../../../components/editor/forumEditorHtml";
import { CorMark, FundoMark, TamMark } from "../../../../components/editor/forumEditorMarks";
import { normalizeForumMath } from "../../../../components/forumMath";
import { uploadImagemForum } from "../../../hooks/useForum";

const PALETA = [
  "#ef4444", "#f97316", "#eab308", "#22c55e", "#06b6d4",
  "#3b82f6", "#8b5cf6", "#ec4899", "#ffffff", "#94a3b8",
];

const TAMANHOS = [
  { rotulo: "Pequeno", px: 12 },
  { rotulo: "Grande", px: 18 },
  { rotulo: "Muito grande", px: 24 },
];

type Menu = "cor" | "fundo" | "tam" | null;

interface CommentEditorProps {
  onSubmit: (texto: string) => Promise<void> | void;
  onCancel?: () => void;
  submitting?: boolean;
  valorInicial?: string;
  autoFocus?: boolean;
  placeholder?: string;
}

/** valorInicial pode ser HTML (editor novo) ou markdown legado. Nunca perde conteúdo. */
function conteudoInicial(valor: string): string {
  const v = valor.trim();
  if (!v) return "";
  if (pareceHtml(v)) return v;
  try {
    return markdownParaHtml(v);
  } catch {
    return `<p>${escaparHtml(v)}</p>`;
  }
}

export function CommentEditor({
  onSubmit, onCancel, submitting = false, valorInicial = "", autoFocus = false,
  placeholder = "Escreva aqui seu comentário",
}: CommentEditorProps) {
  const [menu, setMenu] = useState<Menu>(null);
  const [uploads, setUploads] = useState(0);
  const [temConteudo, setTemConteudo] = useState(!!valorInicial.trim());

  const editor = useEditor({
    immediatelyRender: false,
    autofocus: autoFocus,
    extensions: [
      StarterKit,
      Image,
      Mathematics.configure({
        katexOptions: { throwOnError: false },
        inlineOptions: {
          onClick: (node, pos) => {
            const latex = prompt("Editar fórmula (LaTeX):", node.attrs.latex);
            if (latex) editor?.chain().setNodeSelection(pos).updateInlineMath({ latex }).focus().run();
          },
        },
      }),
      Placeholder.configure({ placeholder }),
      CorMark, FundoMark, TamMark,
    ],
    content: conteudoInicial(valorInicial),
    onCreate: ({ editor: e }) => {
      migrateMathStrings(e); // $...$ do conteúdo legado viram nós de fórmula
      setTemConteudo(!htmlEditorVazio(e.getHTML()));
    },
    onUpdate: ({ editor: e }) => setTemConteudo(!htmlEditorVazio(e.getHTML())),
    editorProps: {
      transformPastedHTML: (html) => limparImagensExternas(html),
      handlePaste: (_view, event) => {
        const imagens = event.clipboardData ? imagensDoClipboard(event.clipboardData) : [];
        if (!imagens.length) return false; // segue o paste nativo do TipTap
        event.preventDefault();
        void subirImagens(imagens);
        return true;
      },
    },
  });

  /** Preview instantâneo (blob local) → upload MinIO → troca o src pela URL nossa. */
  async function subirImagens(arquivos: File[]) {
    if (!editor) return;
    for (const file of arquivos) {
      const tempSrc = URL.createObjectURL(file);
      setUploads((n) => n + 1);
      editor.chain().focus().setImage({ src: tempSrc, alt: "enviando…" }).run();
      try {
        const url = await uploadImagemForum(file);
        trocarSrcImagem(tempSrc, url);
      } catch {
        removerImagem(tempSrc);
        editor.chain().focus().insertContent("<p><em>(falha ao subir imagem)</em></p>").run();
      } finally {
        URL.revokeObjectURL(tempSrc);
        setUploads((n) => n - 1);
      }
    }
  }

  function trocarSrcImagem(de: string, para: string) {
    if (!editor) return;
    const { tr, doc } = editor.state;
    doc.descendants((node, pos) => {
      if (node.type.name === "image" && node.attrs.src === de) {
        tr.setNodeMarkup(pos, undefined, { ...node.attrs, src: para, alt: "imagem" });
      }
    });
    editor.view.dispatch(tr);
  }

  function removerImagem(src: string) {
    if (!editor) return;
    const { tr, doc } = editor.state;
    doc.descendants((node, pos) => {
      if (node.type.name === "image" && node.attrs.src === src) {
        tr.delete(pos, pos + node.nodeSize);
      }
    });
    editor.view.dispatch(tr);
  }

  function aoEscolherImagem(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) void subirImagens([file]);
  }

  function inserirFormula() {
    if (!editor) return;
    const latex = prompt("Fórmula (LaTeX):", "");
    if (latex) editor.chain().focus().insertInlineMath({ latex }).run();
  }

  async function publicar() {
    if (!editor) return;
    const html = mathHtmlParaDelimitadores(editor.getHTML());
    if (htmlEditorVazio(html)) return;
    await onSubmit(normalizeForumMath(html));
    editor.commands.clearContent(true);
    setTemConteudo(false);
  }

  function Btn({ titulo, ativo = false, onClick, children }: {
    titulo: string; ativo?: boolean; onClick: () => void; children: React.ReactNode;
  }) {
    return (
      <button type="button" title={titulo} onClick={onClick}
        className={`px-1.5 rounded hover:text-fg ${ativo ? "bg-surface text-fg" : ""}`}>
        {children}
      </button>
    );
  }

  function MenuPaleta({ aoEscolher, aoRemover }: { aoEscolher: (c: string) => void; aoRemover: () => void }) {
    return (
      <div className="absolute left-0 top-full z-30 mt-1 grid w-max grid-cols-5 gap-1.5 rounded-md border border-border bg-surface p-2 shadow-xl">
        {PALETA.map((c) => (
          <button key={c} type="button" title={c} onClick={() => aoEscolher(c)}
            className="h-5 w-5 rounded border border-white/20 transition-transform hover:scale-110"
            style={{ backgroundColor: c }} />
        ))}
        <button type="button" title="Remover" onClick={aoRemover}
          className="flex h-5 w-5 items-center justify-center rounded border border-white/20 text-[10px] text-fg-faint hover:text-fg">✕</button>
      </div>
    );
  }

  if (!editor) {
    // SSR/primeiro paint: reserva o espaço do editor (regra: dados não pulam)
    return <div className="min-h-[10rem] rounded-lg border border-border bg-surface-2/40" />;
  }

  return (
    <div className="forum-editor rounded-lg border border-border bg-surface-2/40">
      <div className="relative flex flex-wrap items-center gap-1 border-b border-border/60 px-2 py-1.5 text-fg-faint">
        <Btn titulo="Desfazer" onClick={() => editor.chain().focus().undo().run()}>↶</Btn>
        <Btn titulo="Refazer" onClick={() => editor.chain().focus().redo().run()}>↷</Btn>
        <span className="mx-1 h-4 w-px bg-border" />
        <Btn titulo="Negrito" ativo={editor.isActive("bold")} onClick={() => editor.chain().focus().toggleBold().run()}><b>B</b></Btn>
        <Btn titulo="Itálico" ativo={editor.isActive("italic")} onClick={() => editor.chain().focus().toggleItalic().run()}><i>I</i></Btn>
        <Btn titulo="Lista" ativo={editor.isActive("bulletList")} onClick={() => editor.chain().focus().toggleBulletList().run()}>≡</Btn>
        <Btn titulo="Citação" ativo={editor.isActive("blockquote")} onClick={() => editor.chain().focus().toggleBlockquote().run()}>❝</Btn>
        <Btn titulo="Fórmula" onClick={inserirFormula}><span className="font-mono">∑</span></Btn>
        <label title="Imagem" className="cursor-pointer px-1.5 hover:text-fg">
          {uploads > 0 ? "…" : "🖼"}
          <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden" onChange={aoEscolherImagem} />
        </label>
        <span className="mx-1 h-4 w-px bg-border" />
        <div className="relative">
          <Btn titulo="Cor da letra" ativo={editor.isActive("cor") || menu === "cor"} onClick={() => setMenu(menu === "cor" ? null : "cor")}>
            <span className="border-b-2 border-primary font-bold">A</span>
          </Btn>
          {menu === "cor" && (
            <MenuPaleta
              aoEscolher={(c) => { setMenu(null); editor.chain().focus().setCor(c).run(); }}
              aoRemover={() => { setMenu(null); editor.chain().focus().unsetCor().run(); }} />
          )}
        </div>
        <div className="relative">
          <Btn titulo="Cor do fundo" ativo={editor.isActive("fundo") || menu === "fundo"} onClick={() => setMenu(menu === "fundo" ? null : "fundo")}>
            <span className="rounded bg-primary/30 px-1 font-bold">A</span>
          </Btn>
          {menu === "fundo" && (
            <MenuPaleta
              aoEscolher={(c) => { setMenu(null); editor.chain().focus().setFundo(c).run(); }}
              aoRemover={() => { setMenu(null); editor.chain().focus().unsetFundo().run(); }} />
          )}
        </div>
        <div className="relative">
          <Btn titulo="Tamanho da letra" ativo={editor.isActive("tam") || menu === "tam"} onClick={() => setMenu(menu === "tam" ? null : "tam")}>
            <span className="font-bold">A</span><span className="text-[10px] font-bold">a</span>
          </Btn>
          {menu === "tam" && (
            <div className="absolute left-0 top-full z-30 mt-1 w-max rounded-md border border-border bg-surface py-1 shadow-xl">
              {TAMANHOS.map(({ rotulo, px }) => (
                <button key={px} type="button"
                  onClick={() => { setMenu(null); editor.chain().focus().setTam(px).run(); }}
                  className="block w-full px-3 py-1 text-left hover:bg-white/5 hover:text-fg"
                  style={{ fontSize: px }}>
                  {rotulo}
                </button>
              ))}
              <button type="button"
                onClick={() => { setMenu(null); editor.chain().focus().unsetTam().run(); }}
                className="block w-full px-3 py-1 text-left text-xs text-fg-faint hover:bg-white/5 hover:text-fg">
                Normal
              </button>
            </div>
          )}
        </div>
      </div>

      {menu && <div className="fixed inset-0 z-20" onClick={() => setMenu(null)} />}

      <EditorContent editor={editor} />

      <div className="flex items-center gap-2 border-t border-border/60 px-2 py-1.5">
        <button type="button" onClick={publicar} disabled={submitting || uploads > 0 || !temConteudo}
          className="rounded bg-primary px-3 py-1 text-xs font-semibold text-black disabled:opacity-50">
          {submitting ? "Publicando…" : uploads > 0 ? "Enviando imagem…" : "Publicar"}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="text-xs text-fg-faint hover:text-fg">Cancelar</button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Estilos do editor** — acrescentar ao FIM de `fontend/app/globals.css`:

```css
/* ─── Editor WYSIWYG do fórum (TipTap) ─────────────────────────────── */
.forum-editor .tiptap {
  min-height: 7rem;
  padding: 0.5rem 0.75rem;
  font-size: 0.875rem;
  line-height: 1.625;
  color: var(--color-fg, #e5e5e5);
  outline: none;
  word-break: break-word;
}
.forum-editor .tiptap p { margin: 0 0 0.5rem; }
.forum-editor .tiptap p:last-child { margin-bottom: 0; }
.forum-editor .tiptap strong { font-weight: 600; }
.forum-editor .tiptap ul { list-style: disc; padding-left: 1.25rem; margin-bottom: 0.5rem; }
.forum-editor .tiptap ol { list-style: decimal; padding-left: 1.25rem; margin-bottom: 0.5rem; }
.forum-editor .tiptap blockquote {
  border-left: 4px solid color-mix(in srgb, var(--color-primary, #06b6d4) 40%, transparent);
  padding-left: 0.75rem;
  font-style: italic;
  margin: 0.5rem 0;
}
.forum-editor .tiptap img {
  max-width: 100%;
  border-radius: 0.5rem;
  margin: 0.5rem 0;
  border: 1px solid var(--color-border, #333);
}
.forum-editor .tiptap img.ProseMirror-selectednode {
  outline: 2px solid var(--color-primary, #06b6d4);
}
.forum-editor .tiptap p.is-editor-empty:first-child::before {
  content: attr(data-placeholder);
  float: left;
  height: 0;
  pointer-events: none;
  color: var(--color-fg-faint, #777);
}
.forum-editor .tiptap .tiptap-mathematics-render {
  padding: 0 2px;
  border-radius: 3px;
  cursor: pointer;
}
.forum-editor .tiptap .tiptap-mathematics-render:hover {
  background: color-mix(in srgb, var(--color-primary, #06b6d4) 15%, transparent);
}
```

Nota: conferir os nomes reais das CSS vars do tema em `globals.css` (`--color-*` vs tokens do Tailwind 4) e usar os existentes; os fallbacks acima mantêm funcional de qualquer forma.

- [ ] **Step 3: Typecheck + lint** — `pnpm exec tsc --noEmit && pnpm lint` → sem erros (warnings pré-existentes ok). Se o import `{ Placeholder } from "@tiptap/extensions"` falhar, trocar por `Placeholder from "@tiptap/extension-placeholder"` (ver Task 1 Step 2).

- [ ] **Step 4: Testes existentes continuam verdes** — `node --test app/components/*.test.mjs app/components/editor/*.test.mjs` → todos pass.

- [ ] **Step 5: Commit** — `git add -A fontend/app && git commit -m "feat(forum): CommentEditor WYSIWYG TipTap — formatação e imagens ao vivo no corpo"`

---

### Task 5: Pipeline de render cobre o HTML emitido pelo editor

**Files:**
- Modify: `fontend/app/components/forumMarkdown.test.mjs` (novos casos)
- Modify (se necessário): `fontend/app/components/forumMarkdown.ts`

**Interfaces:**
- Consumes: pipeline existente (`forumRemarkPlugins`, `forumRehypePlugins`).
- Produces: garantia de que blockquote, listas, spans aninhados e `<em>/<strong>` do TipTap renderizam; nada perigoso passa.

- [ ] **Step 1: Novos testes**

```js
test("HTML emitido pelo editor TipTap renderiza inteiro", () => {
  const html = render(
    '<p><strong>a</strong> <em>b</em></p><blockquote><p>cit</p></blockquote>'
    + '<ul><li>um</li></ul>'
    + '<p><span data-fundo="#eab308"><span data-cor="#ef4444">forte</span></span></p>'
  );
  assert.match(html, /<strong>a<\/strong>/);
  assert.match(html, /<blockquote>/);
  assert.match(html, /<li>um<\/li>/);
  assert.match(html, /data-fundo="#eab308"/);
  assert.match(html, /data-cor="#ef4444"/);
});

test("style inline salvo pelo editor é descartado no render", () => {
  const html = render('<p><span data-cor="#ef4444" style="color:#ef4444;position:fixed">x</span></p>');
  assert.doesNotMatch(html, /position:fixed/);
  assert.match(html, /data-cor="#ef4444"/);
});
```

- [ ] **Step 2: Rodar** — `node --test app/components/forumMarkdown.test.mjs`. Se falhar por tag fora do schema (ex.: blockquote está no default, mas conferir), adicionar a tag ao `schema.tagNames` em `forumMarkdown.ts` e re-rodar.

- [ ] **Step 3: Commit** — `git commit -am "test(forum): pipeline cobre HTML do editor TipTap (style de usuário descartado)"`

---

### Task 6: Remover turndown (não usado mais)

**Files:**
- Modify: `fontend/package.json`

- [ ] **Step 1: Confirmar que nada mais importa turndown** — `grep -rn "turndown" fontend/app fontend/lib` → vazio (o CommentEditor novo não usa; TipTap absorve HTML colado nativamente).
- [ ] **Step 2: Remover** — `cd fontend && pnpm remove turndown @types/turndown`.
- [ ] **Step 3: Verificar** — `pnpm exec tsc --noEmit && pnpm lint` → ok.
- [ ] **Step 4: Commit** — `git add fontend/package.json fontend/pnpm-lock.yaml && git commit -m "chore(forum): remove turndown (paste rico agora é nativo do TipTap)"`

---

### Task 7: Verificação end-to-end no navegador (Playwright + harness)

**Files:**
- Create (temporário, NUNCA commitado): `fontend/app/dev-editor/page.tsx`

**Interfaces:**
- Consumes: CommentEditor final; stub de upload em `127.0.0.1:8011` (mesmo padrão da verificação anterior: POST `/api/q/forum/upload` → `{url}`; GET `/api/q/forum/imagem/...` → PNG).

- [ ] **Step 1: Harness** — página `"use client"` que renderiza `<CommentEditor onSubmit={(t) => { window.__publicado = t; }} />` e um segundo `<CommentEditor valorInicial={'**legado** com $E=mc^2$ e <span data-cor="#ef4444">cor</span>'} onSubmit={...} />` para o caso legado. Subir stub python na 8011 e `pnpm dev -p 3002`. Bypass do proxy de auth: cookie `better-auth.session_token=dev-harness`.
- [ ] **Step 2: Verificar formatação ao vivo NO CORPO** — digitar texto, selecionar palavra, aplicar cor/fundo/tamanho pela toolbar; assert no DOM do `.tiptap`: `span[data-cor]` com `style` de cor visível (getComputedStyle), sem nenhum código visível no texto.
- [ ] **Step 3: Verificar imagem colada inline** — despachar `ClipboardEvent` com File PNG (+ text/html com img externa junto, como o "Copiar imagem" real); assert: `img` aparece IMEDIATAMENTE no `.tiptap` (blob:), depois src troca para `http://localhost:8011/api/q/forum/imagem/...`; botão mostra "Enviando imagem…" enquanto `uploads > 0`.
- [ ] **Step 4: Verificar payload do Publicar** — inserir fórmula via ∑ (prompt → stub via `page.on('dialog')` ou override de `window.prompt`), publicar; assert em `window.__publicado`: contém `<span data-cor="#hex">`, `$latex$` (NÃO `data-type="inline-math"`), `<img src=".../api/q/forum/imagem/...">`, e NENHUM `blob:`.
- [ ] **Step 5: Verificar carga de legado** — no segundo editor: `strong` renderizado, fórmula como nó KaTeX visível, span colorido; publicar e conferir que `$E=mc^2$` volta como delimitador.
- [ ] **Step 6: Verificar colar HTML com img externa sem blob** — despachar paste só com text/html contendo `<img src="https://externa...">` + texto; assert: texto entra, img externa NÃO entra no doc.
- [ ] **Step 7: Screenshot final para o usuário; derrubar servidores; `rm -rf fontend/app/dev-editor` e artefatos.** `git status` limpo de temporários.

---

### Task 8: Merge, deploy e limpeza

- [ ] **Step 1:** `pnpm lint && pnpm exec tsc --noEmit && node --test app/components/*.test.mjs app/components/editor/*.test.mjs` — tudo verde no worktree.
- [ ] **Step 2:** Commit final se houver resto; do checkout principal (`/home/wital/studia`, que permanece na `main`): `git merge worktree-forum-editor-wysiwyg && git push`.
- [ ] **Step 3:** `./build.sh` (background; aguardar exit 0; conferir `stack deployed` no log).
- [ ] **Step 4:** Remover worktree (ExitWorktree remove) + `git worktree list` limpo.
- [ ] **Step 5:** Smoke prod: `curl -s -o /dev/null -w "%{http_code}" https://studia.witdev.com.br` → 200.

---

## Self-review do plano

- **Cobertura do spec:** editor TipTap (T4), marks/serialização compatível (T3), math↔`$` + legado md→HTML + strip img externa (T2), imagens coladas com preview e upload (T4+T7), render inalterado com garantia por teste (T5), remoção do preview e do turndown (T4+T6), Playwright (T7), fluxo worktree→deploy (T1+T8). Riscos do spec endereçados: versões (T1 Step 2-3), math em conteúdo carregado via `migrateMathStrings` (T4 onCreate; aceite no T7 Step 5).
- **Placeholders:** nenhum — todo step de código tem o código.
- **Consistência de tipos/nomes:** comandos `setCor/setFundo/setTam` declarados no module augmentation (T3) e usados na toolbar (T4); helpers de T2 importados com os mesmos nomes em T4.

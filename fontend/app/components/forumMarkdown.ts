import type { Element, ElementContent, Root } from "hast";
import type { Options } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";

const tableTags = ["table", "thead", "tbody", "tr", "th", "td"];

const schema = {
  ...defaultSchema,
  tagNames: Array.from(new Set([...(defaultSchema.tagNames ?? []), ...tableTags])),
  attributes: {
    ...defaultSchema.attributes,
    // data-cor/data-fundo/data-tam: formatação de texto do editor do fórum.
    // Os VALORES são validados no render (ForumContent), nunca viram style cru aqui.
    span: [
      ...(defaultSchema.attributes?.span ?? []),
      ["className", "math", "math-inline", "math-display"],
      "dataCor",
      "dataFundo",
      "dataTam",
    ],
    div: [...(defaultSchema.attributes?.div ?? []), ["className", "math", "math-display"]],
    img: [...(defaultSchema.attributes?.img ?? []), "src", "alt", "title"],
    th: [...(defaultSchema.attributes?.th ?? []), "align"],
    td: [...(defaultSchema.attributes?.td ?? []), "align"],
  },
};

// ─── rehypeMathDelimitadores ────────────────────────────────────────────────
// O remark-math só enxerga $...$ em TEXTO markdown; fórmula dentro de HTML cru
// (comentário salvo pelo editor WYSIWYG, formato <p>...</p>) ficava literal.
// Este plugin roda DEPOIS do rehype-raw: nos nós de texto que sobraram com
// $...$/$$...$$ (só existem vindos de HTML — no markdown puro o remark-math já
// consumiu), converte para os spans de math que o rehype-katex renderiza.
// Regras de fronteira espelham o remark-math/normalizeForumMath: abre $ não
// precedido de alfanumérico e seguido de não-espaço; fecha $ não precedido de
// espaço; inline não cruza linha; \$ escapado é ignorado.

const TAGS_SEM_MATH = new Set(["code", "pre", "script", "style", "textarea"]);

function escapado(valor: string, i: number): boolean {
  let n = 0;
  for (let j = i - 1; j >= 0 && valor[j] === "\\"; j -= 1) n += 1;
  return n % 2 === 1;
}

function noMath(corpo: string, display: boolean): Element {
  return {
    type: "element",
    tagName: "span",
    properties: { className: display ? ["math", "math-display"] : ["math", "math-inline"] },
    children: [{ type: "text", value: corpo }],
  };
}

function partirTextoEmMath(valor: string): ElementContent[] | null {
  const partes: ElementContent[] = [];
  let texto = "";
  let i = 0;
  let achou = false;
  while (i < valor.length) {
    if (valor[i] !== "$" || escapado(valor, i)) {
      texto += valor[i];
      i += 1;
      continue;
    }
    const display = valor[i + 1] === "$";
    const delim = display ? "$$" : "$";
    const prev = valor[i - 1] ?? "";
    const next = valor[i + delim.length] ?? "";
    if (!display && (/[A-Za-z0-9]/.test(prev) || next === "" || /\s/.test(next))) {
      texto += valor[i];
      i += 1;
      continue;
    }
    let fim = -1;
    for (let j = i + delim.length; j < valor.length; j += 1) {
      if (!display && (valor[j] === "\n" || valor[j] === "\r")) break;
      if (valor.startsWith(delim, j) && !escapado(valor, j)) {
        if (!display && /\s/.test(valor[j - 1] ?? "")) continue;
        fim = j;
        break;
      }
    }
    const corpo = fim === -1 ? "" : valor.slice(i + delim.length, fim);
    if (fim === -1 || !corpo.trim()) {
      texto += valor[i];
      i += 1;
      continue;
    }
    if (texto) partes.push({ type: "text", value: texto });
    texto = "";
    partes.push(noMath(corpo, display));
    achou = true;
    i = fim + delim.length;
  }
  if (!achou) return null;
  if (texto) partes.push({ type: "text", value: texto });
  return partes;
}

function visitarMath(node: Root | Element): void {
  if (node.type === "element") {
    if (TAGS_SEM_MATH.has(node.tagName)) return;
    const cls = node.properties?.className;
    if (Array.isArray(cls) && cls.some((c) => String(c).startsWith("math") || String(c).startsWith("katex"))) return;
  }
  const filhos = node.children as ElementContent[] | undefined;
  if (!filhos) return;
  for (let i = filhos.length - 1; i >= 0; i -= 1) {
    const filho = filhos[i];
    if (filho.type === "text") {
      if (filho.value.includes("$")) {
        const partes = partirTextoEmMath(filho.value);
        if (partes) filhos.splice(i, 1, ...partes);
      }
    } else if (filho.type === "element") {
      visitarMath(filho);
    }
  }
}

function rehypeMathDelimitadores() {
  return (tree: Root) => {
    visitarMath(tree);
  };
}

export const forumRemarkPlugins: NonNullable<Options["remarkPlugins"]> = [remarkGfm, remarkMath];
// rehype-raw ANTES do sanitize: o HTML digitado/colado vira nós reais e o
// sanitize remove tudo que não está no schema — a ordem é o que mantém XSS-safe.
// rehypeMathDelimitadores entre eles: pesca $...$ que sobrou em texto de HTML.
export const forumRehypePlugins: NonNullable<Options["rehypePlugins"]> = [
  rehypeRaw,
  rehypeMathDelimitadores,
  [rehypeSanitize, schema],
  rehypeKatex,
];

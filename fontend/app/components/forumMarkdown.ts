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

export const forumRemarkPlugins: NonNullable<Options["remarkPlugins"]> = [remarkGfm, remarkMath];
// rehype-raw ANTES do sanitize: o HTML digitado/colado vira nós reais e o
// sanitize remove tudo que não está no schema — a ordem é o que mantém XSS-safe.
export const forumRehypePlugins: NonNullable<Options["rehypePlugins"]> = [
  rehypeRaw,
  [rehypeSanitize, schema],
  rehypeKatex,
];

import type { Options } from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";

const tableTags = ["table", "thead", "tbody", "tr", "th", "td"];

const schema = {
  ...defaultSchema,
  tagNames: Array.from(new Set([...(defaultSchema.tagNames ?? []), ...tableTags])),
  attributes: {
    ...defaultSchema.attributes,
    span: [...(defaultSchema.attributes?.span ?? []), ["className", "math", "math-inline", "math-display"]],
    div: [...(defaultSchema.attributes?.div ?? []), ["className", "math", "math-display"]],
    img: [...(defaultSchema.attributes?.img ?? []), "src", "alt", "title"],
    th: [...(defaultSchema.attributes?.th ?? []), "align"],
    td: [...(defaultSchema.attributes?.td ?? []), "align"],
  },
};

export const forumRemarkPlugins: NonNullable<Options["remarkPlugins"]> = [remarkGfm, remarkMath];
export const forumRehypePlugins: NonNullable<Options["rehypePlugins"]> = [[rehypeSanitize, schema], rehypeKatex];

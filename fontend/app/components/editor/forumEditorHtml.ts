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
  if (/<img\b/i.test(html)) return false;
  const texto = html.replace(/<[^>]*>/g, "").trim();
  return texto.length === 0;
}

const TAGS_HTML = /<(p|div|span|ul|ol|li|blockquote|h[1-6]|img|table|pre|strong|em)\b/i;

/** Heurística: conteúdo salvo pelo editor novo é HTML; legado é markdown. */
export function pareceHtml(texto: string): boolean {
  return TAGS_HTML.test(texto);
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

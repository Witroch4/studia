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

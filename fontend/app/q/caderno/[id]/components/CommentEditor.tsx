"use client";

import { useDeferredValue, useRef, useState } from "react";
import TurndownService from "turndown";
import ForumContent from "../../../../components/ForumContent";
import { imagensDoClipboard } from "../../../../components/forumClipboard";
import { normalizeForumMath } from "../../../../components/forumMath";
import { uploadImagemForum } from "../../../hooks/useForum";

// Converte HTML colado (chat do Gemini, Word, páginas) em markdown, preservando
// títulos, negrito/itálico, listas numeradas e citações — como o editor do TC.
const turndown = new TurndownService({
  headingStyle: "atx",
  bulletListMarker: "-",
  codeBlockStyle: "fenced",
  emDelimiter: "_",
});

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

export function CommentEditor({
  onSubmit, onCancel, submitting = false, valorInicial = "", autoFocus = false,
  placeholder = "Escreva aqui seu comentário",
}: CommentEditorProps) {
  const [texto, setTexto] = useState(valorInicial);
  const [enviandoImg, setEnviandoImg] = useState(false);
  const [menu, setMenu] = useState<Menu>(null);
  const ref = useRef<HTMLTextAreaElement | null>(null);
  const seqImg = useRef(0);
  // preview ao vivo: adia o valor pra não travar a digitação com KaTeX/markdown
  const textoPreview = useDeferredValue(texto);

  function envolver(antes: string, depois = antes) {
    const el = ref.current;
    if (!el) return;
    const [a, b] = [el.selectionStart, el.selectionEnd];
    const novo = texto.slice(0, a) + antes + texto.slice(a, b) + depois + texto.slice(b);
    setTexto(novo);
    requestAnimationFrame(() => { el.focus(); el.selectionStart = el.selectionEnd = b + antes.length + depois.length; });
  }

  function inserir(trecho: string) {
    const el = ref.current;
    const pos = el ? el.selectionStart : texto.length;
    setTexto(texto.slice(0, pos) + trecho + texto.slice(pos));
  }

  function formatar(attr: "data-cor" | "data-fundo" | "data-tam", valor: string) {
    setMenu(null);
    envolver(`<span ${attr}="${valor}">`, "</span>");
  }

  // Sobe imagens (coladas ou escolhidas) pro MinIO: insere um marcador no
  // cursor na hora e o troca pela URL nossa quando o upload termina — a URL
  // externa nunca entra no texto (seria bloqueada pelo sanitizador).
  async function subirImagens(arquivos: File[]) {
    if (!arquivos.length) return;
    const el = ref.current;
    const start = el ? el.selectionStart : texto.length;
    const end = el ? el.selectionEnd : texto.length;
    const entradas = arquivos.map((file) => {
      seqImg.current += 1;
      return { file, marcador: `_(enviando imagem ${seqImg.current}…)_` };
    });
    const bloco = entradas.map((e) => e.marcador).join("\n");
    setEnviandoImg(true);
    setTexto((t) => t.slice(0, start) + bloco + t.slice(end));
    try {
      await Promise.all(entradas.map(async ({ file, marcador }) => {
        try {
          const url = await uploadImagemForum(file);
          setTexto((t) => t.replace(marcador, `![imagem](${url})`));
        } catch {
          setTexto((t) => t.replace(marcador, "_(falha ao subir imagem)_"));
        }
      }));
    } finally {
      setEnviandoImg(false);
    }
  }

  function aoColar(e: React.ClipboardEvent<HTMLTextAreaElement>) {
    // 1) imagem no clipboard (Copiar imagem / print screen) → upload pro MinIO
    const imagens = imagensDoClipboard(e.clipboardData);
    if (imagens.length) {
      e.preventDefault();
      void subirImagens(imagens);
      return;
    }
    // 2) rich text → markdown via turndown
    const html = e.clipboardData.getData("text/html");
    if (!html) return; // sem rich text → paste nativo (texto puro)
    let md: string;
    try {
      md = turndown.turndown(html).trim();
    } catch {
      md = "";
    }
    if (!md) return; // conversão vazia/erro → deixa o paste nativo seguir
    e.preventDefault();
    md = normalizeForumMath(md);
    const el = ref.current;
    const start = el ? el.selectionStart : texto.length;
    const end = el ? el.selectionEnd : texto.length;
    const novo = texto.slice(0, start) + md + texto.slice(end);
    setTexto(novo);
    requestAnimationFrame(() => {
      if (!el) return;
      el.focus();
      el.selectionStart = el.selectionEnd = start + md.length;
    });
  }

  function aoEscolherImagem(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (file) void subirImagens([file]);
  }

  async function publicar() {
    const t = normalizeForumMath(texto.trim());
    if (!t) return;
    await onSubmit(t);
    setTexto("");
  }

  function MenuPaleta({ attr }: { attr: "data-cor" | "data-fundo" }) {
    return (
      <div className="absolute left-0 top-full z-30 mt-1 grid w-max grid-cols-5 gap-1.5 rounded-md border border-border bg-surface p-2 shadow-xl">
        {PALETA.map((c) => (
          <button key={c} type="button" title={c}
            onClick={() => formatar(attr, c)}
            className="h-5 w-5 rounded border border-white/20 transition-transform hover:scale-110"
            style={{ backgroundColor: c }} />
        ))}
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-surface-2/40">
      <div className="relative flex flex-wrap items-center gap-1 border-b border-border/60 px-2 py-1.5 text-fg-faint">
        <button type="button" title="Negrito" onClick={() => envolver("**")} className="px-1.5 hover:text-fg font-bold">B</button>
        <button type="button" title="Itálico" onClick={() => envolver("_")} className="px-1.5 hover:text-fg italic">I</button>
        <button type="button" title="Lista" onClick={() => inserir("\n- ")} className="px-1.5 hover:text-fg">≡</button>
        <button type="button" title="Fórmula" onClick={() => envolver("$$", "$$")} className="px-1.5 hover:text-fg font-mono">∑</button>
        <label title="Imagem" className="px-1.5 hover:text-fg cursor-pointer">
          {enviandoImg ? "…" : "🖼"}
          <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden" onChange={aoEscolherImagem} />
        </label>

        <span className="mx-1 h-4 w-px bg-border" />

        <div className="relative">
          <button type="button" title="Cor da letra" onClick={() => setMenu(menu === "cor" ? null : "cor")}
            className={`px-1.5 font-bold hover:text-fg ${menu === "cor" ? "text-fg" : ""}`}>
            <span className="border-b-2 border-primary">A</span>
          </button>
          {menu === "cor" && <MenuPaleta attr="data-cor" />}
        </div>

        <div className="relative">
          <button type="button" title="Cor do fundo" onClick={() => setMenu(menu === "fundo" ? null : "fundo")}
            className={`px-1.5 hover:text-fg ${menu === "fundo" ? "text-fg" : ""}`}>
            <span className="rounded bg-primary/30 px-1 font-bold">A</span>
          </button>
          {menu === "fundo" && <MenuPaleta attr="data-fundo" />}
        </div>

        <div className="relative">
          <button type="button" title="Tamanho da letra" onClick={() => setMenu(menu === "tam" ? null : "tam")}
            className={`px-1.5 hover:text-fg ${menu === "tam" ? "text-fg" : ""}`}>
            <span className="font-bold">A</span><span className="text-[10px] font-bold">a</span>
          </button>
          {menu === "tam" && (
            <div className="absolute left-0 top-full z-30 mt-1 w-max rounded-md border border-border bg-surface py-1 shadow-xl">
              {TAMANHOS.map(({ rotulo, px }) => (
                <button key={px} type="button"
                  onClick={() => formatar("data-tam", String(px))}
                  className="block w-full px-3 py-1 text-left hover:bg-white/5 hover:text-fg"
                  style={{ fontSize: px }}>
                  {rotulo}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {menu && <div className="fixed inset-0 z-20" onClick={() => setMenu(null)} />}

      <textarea
        ref={ref}
        value={texto}
        autoFocus={autoFocus}
        onChange={(e) => setTexto(e.target.value)}
        onPaste={aoColar}
        placeholder={placeholder}
        rows={4}
        className="w-full resize-y bg-transparent px-3 py-2 text-sm text-fg outline-none placeholder:text-fg-faint"
      />

      <div className="border-t border-border/60 px-3 py-2">
        <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-fg-faint">Pré-visualização</div>
        {textoPreview.trim()
          ? <ForumContent content={textoPreview} />
          : <p className="text-xs text-fg-faint">O que você escrever aparece aqui já formatado.</p>}
      </div>

      <div className="flex items-center gap-2 border-t border-border/60 px-2 py-1.5">
        <button type="button" onClick={publicar} disabled={submitting || enviandoImg || !texto.trim()}
          className="rounded bg-primary px-3 py-1 text-xs font-semibold text-black disabled:opacity-50">
          {submitting ? "Publicando…" : enviandoImg ? "Enviando imagem…" : "Publicar"}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="text-xs text-fg-faint hover:text-fg">Cancelar</button>
        )}
      </div>
    </div>
  );
}

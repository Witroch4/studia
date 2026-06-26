"use client";

import { useRef, useState } from "react";
import TurndownService from "turndown";
import ForumContent from "../../../../components/ForumContent";
import { uploadImagemForum } from "../../../hooks/useForum";

// Converte HTML colado (chat do Gemini, Word, páginas) em markdown, preservando
// títulos, negrito/itálico, listas numeradas e citações — como o editor do TC.
const turndown = new TurndownService({
  headingStyle: "atx",
  bulletListMarker: "-",
  codeBlockStyle: "fenced",
  emDelimiter: "_",
});

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
  const [aba, setAba] = useState<"escrever" | "preview">("escrever");
  const [enviandoImg, setEnviandoImg] = useState(false);
  const ref = useRef<HTMLTextAreaElement | null>(null);

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

  function aoColar(e: React.ClipboardEvent<HTMLTextAreaElement>) {
    const html = e.clipboardData.getData("text/html");
    if (!html) return; // sem rich text → comportamento padrão (texto puro)
    e.preventDefault();
    let md: string;
    try {
      md = turndown.turndown(html).trim();
    } catch {
      md = e.clipboardData.getData("text/plain");
    }
    if (!md) return;
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

  async function aoEscolherImagem(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = "";
    if (!file) return;
    setEnviandoImg(true);
    try {
      const url = await uploadImagemForum(file);
      inserir(`\n![imagem](${url})\n`);
    } catch {
      inserir("\n_(falha ao subir imagem)_\n");
    } finally {
      setEnviandoImg(false);
    }
  }

  async function publicar() {
    const t = texto.trim();
    if (!t) return;
    await onSubmit(t);
    setTexto("");
  }

  return (
    <div className="rounded-lg border border-border bg-surface-2/40">
      <div className="flex items-center gap-1 border-b border-border/60 px-2 py-1.5 text-fg-faint">
        <button type="button" onClick={() => setAba("escrever")}
          className={`px-2 py-0.5 rounded text-xs ${aba === "escrever" ? "bg-surface text-fg" : "hover:text-fg"}`}>Escrever</button>
        <button type="button" onClick={() => setAba("preview")}
          className={`px-2 py-0.5 rounded text-xs ${aba === "preview" ? "bg-surface text-fg" : "hover:text-fg"}`}>Pré-visualizar</button>
        <span className="mx-1 h-4 w-px bg-border" />
        <button type="button" title="Negrito" onClick={() => envolver("**")} className="px-1.5 hover:text-fg font-bold">B</button>
        <button type="button" title="Itálico" onClick={() => envolver("_")} className="px-1.5 hover:text-fg italic">I</button>
        <button type="button" title="Lista" onClick={() => inserir("\n- ")} className="px-1.5 hover:text-fg">≡</button>
        <button type="button" title="Fórmula" onClick={() => envolver("$$", "$$")} className="px-1.5 hover:text-fg font-mono">∑</button>
        <label title="Imagem" className="px-1.5 hover:text-fg cursor-pointer">
          {enviandoImg ? "…" : "🖼"}
          <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" className="hidden" onChange={aoEscolherImagem} />
        </label>
      </div>

      {aba === "escrever" ? (
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
      ) : (
        <div className="min-h-[6rem] px-3 py-2">
          {texto.trim() ? <ForumContent content={texto} /> : <span className="text-xs text-fg-faint">Nada para pré-visualizar.</span>}
        </div>
      )}

      <div className="flex items-center gap-2 border-t border-border/60 px-2 py-1.5">
        <button type="button" onClick={publicar} disabled={submitting || !texto.trim()}
          className="rounded bg-primary px-3 py-1 text-xs font-semibold text-black disabled:opacity-50">
          {submitting ? "Publicando…" : "Publicar"}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className="text-xs text-fg-faint hover:text-fg">Cancelar</button>
        )}
      </div>
    </div>
  );
}

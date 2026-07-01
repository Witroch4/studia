"use client";

import Image from "@tiptap/extension-image";
import { Mathematics, migrateMathStrings } from "@tiptap/extension-mathematics";
import { Placeholder } from "@tiptap/extensions";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { useState } from "react";
import {
  escaparHtml, htmlEditorVazio, limparImagensExternas,
  markdownParaHtml, mathHtmlParaDelimitadores, pareceHtml,
} from "../../../../components/editor/forumEditorHtml";
import { CorMark, FundoMark, TamMark } from "../../../../components/editor/forumEditorMarks";
import { imagensDoClipboard } from "../../../../components/forumClipboard";
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
    return <div className="min-h-[10.5rem] rounded-lg border border-border bg-surface-2/40" />;
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

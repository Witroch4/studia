"use client";

import { use, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { useHotkeys, ATALHOS_TC } from "../../../hooks/useHotkeys";
import QuestionHtml from "../../../components/QuestionHtml";
import { apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

/**
 * /q/questao/[id] — Resolver questão única.
 *
 * Atalhos integrais do TC (25 teclas), ver /docs/witdev-tec-master-ux.md §2.3
 * e `app/hooks/useHotkeys.ts`.
 */

interface Alternativa {
  id: number;
  letra: string;
  texto_md: string;
  texto_html: string | null;
  correta: boolean | null;
  ordem: number;
}

interface Questao {
  id: number;
  id_externo: number;
  enunciado_md: string;
  enunciado_html: string;
  tipo: string;
  gabarito: string;
  status: string;
  banca: { sigla: string; nome: string } | null;
  orgao: { sigla: string; nome: string } | null;
  cargo: { nome: string; ano: number } | null;
  materia: { nome: string } | null;
  assuntos: { nome: string }[];
  alternativas: Alternativa[];
}

export default function QuestaoPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [selecionada, setSelecionada] = useState<string | null>(null);
  const [resolvida, setResolvida] = useState(false);
  const [favorita, setFavorita] = useState(false);
  const [fontSize, setFontSize] = useState(16);
  const [showAtalhos, setShowAtalhos] = useState(false);

  const { data: q, isPending } = useQuery({
    queryKey: qk.questao(id),
    queryFn: () => apiJson<Questao>(`/api/q/${id}`),
  });

  useHotkeys({
    ArrowLeft: () => router.push(`/q/questao/${Number(id) - 1}`),
    ArrowRight: () => router.push(`/q/questao/${Number(id) + 1}`),
    l: () => alert("Questão aleatória não resolvida (Tecla L)"),
    n: () => alert("Próxima não resolvida (Tecla N)"),
    z: () => alert("Tópico anterior (Tecla Z)"),
    x: () => alert("Tópico seguinte (Tecla X)"),
    v: () => alert("Próxima favorita (Tecla V)"),
    u: () => alert("Próxima anotada (Tecla U)"),
    p: () => {
      const num = prompt("Ir para questão número:");
      if (num) router.push(`/q/questao/${num}`);
    },
    m: () => setFavorita((f) => !f),
    j: () => setFavorita((f) => !f),
    w: () => alert("Anotação (W) — em breve"),
    o: () => alert("Comentário (O) — em breve"),
    f: () => alert("Fórum (F) — em breve"),
    h: () => alert("Desempenho (H) — em breve"),
    i: () => alert("Detalhes (I) — em breve"),
    y: () => alert("Texto associado (Y) — em breve"),
    q: () => alert("Adicionar a caderno (Q) — em breve"),
    "+": () => setFontSize((s) => Math.min(s + 2, 28)),
    "=": () => setFontSize((s) => Math.min(s + 2, 28)),
    "-": () => setFontSize((s) => Math.max(s - 2, 12)),
    "0": () => setFontSize(16),
    ".": () => alert("Pausar relógio (.) — em breve"),
    "?": () => setShowAtalhos(true),
  });

  if (isPending && !q) return <div className="p-8 text-fg-muted">Carregando…</div>;
  if (!q) return null;

  return (
    <div
      className="min-h-screen bg-page text-fg"
      style={{ fontSize }}
    >
      <header className="border-b border-border px-6 py-3 flex items-center gap-4">
        <div className="flex-1">
          <div className="text-xs text-fg-faint">
            Estudo › Caderno IDENCAN CIVIL
          </div>
          <div className="font-semibold">
            Questão Q{q.id_externo}{" "}
            {favorita && <span className="text-yellow-400">⭐</span>}
          </div>
        </div>
        <button onClick={() => setShowAtalhos(true)} className="text-xs text-primary hover:underline">
          Atalhos (?)
        </button>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-6">
        <div className="text-xs text-fg-muted mb-2 flex gap-3 flex-wrap">
          <span className="bg-primary/10 px-2 py-0.5 rounded">{q.banca?.sigla}</span>
          <span>{q.orgao?.sigla} / {q.cargo?.nome} / {q.cargo?.ano}</span>
          <span className="text-fg-faint">{q.materia?.nome} › {q.assuntos[0]?.nome}</span>
        </div>

        <QuestionHtml
          as="article"
          className="prose prose-invert prose-cyan max-w-none mb-4"
          html={q.enunciado_html}
        />

        <ol className="space-y-2 mb-6">
          {q.alternativas.map((alt) => {
            const isCorreta = resolvida && alt.correta;
            const isErrada = resolvida && selecionada === alt.letra && !alt.correta;
            return (
              <li key={alt.id}>
                <button
                  onClick={() => !resolvida && setSelecionada(alt.letra)}
                  disabled={resolvida}
                  className={`w-full text-left flex items-start gap-3 p-3 rounded border transition ${
                    isCorreta ? "border-success bg-success/10" :
                    isErrada ? "border-error bg-error/10" :
                    selecionada === alt.letra ? "border-primary bg-primary/10" :
                    "border-border hover:bg-surface-2"
                  }`}
                >
                  <span className="flex items-center justify-center w-8 h-8 rounded-full bg-surface-2 font-semibold text-sm shrink-0">
                    {alt.letra}
                  </span>
                  <QuestionHtml as="span" html={alt.texto_html || alt.texto_md || ""} />
                </button>
              </li>
            );
          })}
        </ol>

        {!resolvida && (
          <button
            onClick={() => setResolvida(true)}
            disabled={!selecionada}
            className="bg-green-600 hover:bg-green-500 disabled:bg-surface-2 disabled:cursor-not-allowed px-6 py-2 rounded font-semibold"
          >
            RESOLVER QUESTÃO
          </button>
        )}

        {resolvida && (
          <div className="bg-surface-2 border border-border rounded p-4">
            <div className="text-sm">Gabarito oficial: <strong className="text-primary">{q.gabarito}</strong></div>
            {q.status === "ANULADA" && <div className="text-sm text-warning mt-1">⚠ Questão ANULADA</div>}
          </div>
        )}

        <nav className="flex gap-2 mt-6 flex-wrap">
          {([
            ["←", "ArrowLeft", "Anterior"],
            ["→", "ArrowRight", "Próxima"],
            ["🔀", "L", "Aleatória"],
            ["⊟", "N", "Não resolvida"],
            ["↺", "Ctrl+Z", "Desfazer"],
            ["⭐", "M", "Favoritar"],
            ["✏", "W", "Anotar"],
          ] as const).map(([icon, key, label]) => (
            <button
              key={key}
              className="px-3 py-1.5 border border-border hover:bg-surface-2 rounded text-sm flex items-center gap-1"
              title={`${label} (Tecla ${key})`}
            >
              {icon} <span className="text-xs text-fg-faint">{key}</span>
            </button>
          ))}
        </nav>
      </main>

      {showAtalhos && (
        <div
          className="fixed inset-0 bg-black/70 flex items-center justify-center z-50"
          onClick={() => setShowAtalhos(false)}
        >
          <div
            className="bg-surface border border-border rounded-lg p-6 max-w-2xl w-full max-h-[80vh] overflow-y-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-semibold mb-4">Lista das teclas de atalho</h2>
            {(["nav", "acao", "ui"] as const).map((grupo) => (
              <div key={grupo} className="mb-4">
                <h3 className="text-xs uppercase tracking-wider text-primary mb-2">
                  {grupo === "nav" ? "Navegação" : grupo === "acao" ? "Ações" : "Interface"}
                </h3>
                <table className="w-full text-sm">
                  <tbody>
                    {Object.entries(ATALHOS_TC)
                      .filter(([, v]) => v.group === grupo)
                      .map(([k, v]) => (
                        <tr key={k}>
                          <td className="py-1 pr-4 font-mono text-primary">{k}</td>
                          <td className="py-1 text-fg">{v.label}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            ))}
            <button onClick={() => setShowAtalhos(false)} className="mt-4 text-xs text-fg-muted hover:text-fg-strong">
              Fechar (Esc)
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

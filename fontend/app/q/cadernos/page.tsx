"use client";

import { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch } from "@/lib/api";

/**
 * /q/cadernos — "Minhas pastas", hierarquia estilo TecConcursos:
 *   Estudo › Minhas pastas               → lista de pastas
 *   Estudo › Minhas pastas › {pasta}     → cadernos da pasta (?pasta=Nome)
 *
 * Pasta vem por query string (não rota dinâmica) porque nomes de pasta
 * contêm "/" (ex: "Guia OAB / 2026 …"). `?pasta=` (vazio) = sem classificação.
 */

const SEM_CLASSIFICACAO = "Sem classificação";

interface PastaRow {
  pasta: string | null;
  cadernos: number;
  total_questoes: number;
}

interface CadernoRow {
  id: number;
  nome: string;
  total: number;
  pasta: string | null;
  created_at: string | null;
}

interface Desempenho {
  resolvidas: number;
  acertos: number;
  erros: number;
}

function iniciaisPasta(nome: string): string {
  const palavras = nome.replace(/[^\p{L}\p{N} ]/gu, " ").split(/\s+/).filter(Boolean);
  return palavras.slice(0, 2).map((p) => p[0]).join("").toUpperCase() || "📁";
}

function PastasView({ pastas }: { pastas: PastaRow[] }) {
  const router = useRouter();
  return (
    <div className="space-y-3">
      {pastas.length === 0 && (
        <p className="text-sm text-fg-faint italic">
          Nenhum caderno criado ainda. Use <Link href="/q/filtrar" className="text-primary hover:underline">Filtrar Questões</Link>{" "}
          ou monte por um <Link href="/q/guias" className="text-primary hover:underline">Guia de Estudos</Link>.
        </p>
      )}
      {pastas.map((p) => {
        const nome = p.pasta ?? SEM_CLASSIFICACAO;
        const href = `/q/cadernos?pasta=${encodeURIComponent(p.pasta ?? "")}`;
        return (
          <div
            key={nome}
            onClick={() => router.push(href)}
            className="flex items-center gap-4 p-4 rounded-lg border border-border/60 bg-surface hover:border-primary/40 cursor-pointer transition"
          >
            <div className="w-11 h-11 rounded-full bg-gradient-to-br from-cyan-600 to-violet-600 flex items-center justify-center text-sm font-bold shrink-0">
              {p.pasta ? iniciaisPasta(p.pasta) : "📁"}
            </div>
            <div className="flex-1 min-w-0">
              <Link href={href} onClick={(e) => e.stopPropagation()} className="font-semibold text-primary hover:underline truncate block">
                {nome}
              </Link>
              <div className="text-xs text-fg-faint">{p.total_questoes.toLocaleString("pt-BR")} questões</div>
            </div>
            <div className="text-sm text-fg-muted shrink-0">{p.cadernos} caderno{p.cadernos === 1 ? "" : "s"}</div>
          </div>
        );
      })}
    </div>
  );
}

function CadernosView({ pasta }: { pasta: string }) {
  const [cadernos, setCadernos] = useState<CadernoRow[] | null>(null);
  const [desempenho, setDesempenho] = useState<Record<number, Desempenho | "loading">>({});

  useEffect(() => {
    apiFetch(`/api/q/cadernos?pasta=${encodeURIComponent(pasta)}`)
      .then((r) => r.json())
      .then(setCadernos)
      .catch(console.error);
  }, [pasta]);

  async function carregarDesempenho(id: number) {
    setDesempenho((d) => ({ ...d, [id]: "loading" }));
    try {
      const r = await apiFetch(`/api/q/cadernos/${id}/estatisticas`);
      const data = await r.json();
      setDesempenho((d) => ({ ...d, [id]: { resolvidas: data.resolvidas, acertos: data.acertos, erros: data.erros } }));
    } catch (e) {
      console.error(e);
      setDesempenho((d) => {
        const resto = { ...d };
        delete resto[id];
        return resto;
      });
    }
  }

  if (cadernos === null) return <p className="text-sm text-fg-faint">Carregando…</p>;
  if (cadernos.length === 0) return <p className="text-sm text-fg-faint italic">Nenhum caderno nesta pasta.</p>;

  return (
    <div className="space-y-2">
      {cadernos.map((c) => {
        const d = desempenho[c.id];
        return (
          <div
            key={c.id}
            className="flex items-center gap-4 px-4 py-3 rounded-lg border border-border/60 bg-surface hover:border-primary/40 transition"
          >
            <span className="text-fg-faint">🎓</span>
            <div className="flex-1 min-w-0">
              <Link href={`/q/caderno/${c.id}`} className="text-sm font-medium text-fg hover:text-primary hover:underline truncate block">
                {c.nome}
              </Link>
              <div className="text-xs text-fg-faint">
                {c.total.toLocaleString("pt-BR")} questões
                {c.created_at && <> · criado em {new Date(c.created_at).toLocaleDateString("pt-BR")}</>}
              </div>
            </div>
            <div className="text-xs shrink-0">
              {!d && (
                <button onClick={() => carregarDesempenho(c.id)} className="text-primary hover:underline">
                  Carregar desempenho
                </button>
              )}
              {d === "loading" && <span className="text-fg-faint">…</span>}
              {d && d !== "loading" && (
                <span className="text-fg-muted">
                  {d.resolvidas} resolvidas · <span className="text-success">{d.acertos} acertos</span> ·{" "}
                  <span className="text-error">{d.erros} erros</span>
                </span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function MinhasPastasInner() {
  const searchParams = useSearchParams();
  const pastaParam = searchParams.has("pasta") ? (searchParams.get("pasta") ?? "") : null;
  const [pastas, setPastas] = useState<PastaRow[]>([]);

  useEffect(() => {
    apiFetch("/api/q/pastas")
      .then((r) => r.json())
      .then(setPastas)
      .catch(console.error);
  }, []);

  const tituloPasta = pastaParam === null ? null : pastaParam === "" ? SEM_CLASSIFICACAO : pastaParam;

  return (
    <div className="min-h-screen bg-page text-fg">
      <div className="border-b border-border/60 px-6 py-2 flex items-center gap-3 text-xs bg-page">
        <span className="text-fg-faint">Estudo</span>
        <span className="text-fg-faint">›</span>
        {tituloPasta === null ? (
          <span className="text-fg-muted">Minhas pastas</span>
        ) : (
          <>
            <Link href="/q/cadernos" className="text-fg-faint hover:text-primary hover:underline">Minhas pastas</Link>
            <span className="text-fg-faint">›</span>
            <span className="text-fg-muted truncate max-w-[50vw]">{tituloPasta}</span>
          </>
        )}
      </div>

      <main className="max-w-4xl mx-auto px-6 py-6">
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-xl font-semibold">{tituloPasta ?? "Minhas pastas"}</h1>
          <Link
            href="/q/filtrar"
            className="bg-cyan-600 hover:bg-cyan-500 px-4 py-2 rounded text-sm font-semibold"
          >
            NOVO CADERNO
          </Link>
        </div>

        {pastaParam === null ? <PastasView pastas={pastas} /> : <CadernosView pasta={pastaParam} />}
      </main>
    </div>
  );
}

export default function MinhasPastasPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-page" />}>
      <MinhasPastasInner />
    </Suspense>
  );
}

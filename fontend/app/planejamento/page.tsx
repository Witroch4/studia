"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiJson } from "@/lib/api";

interface Caderno {
  id: number;
  nome: string;
  pasta: string | null;
  total: number;
  created_at: string | null;
}

export default function PlanejamentoPage() {
  const [cadernos, setCadernos] = useState<Caderno[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiJson<Caderno[]>("/api/q/cadernos")
      .then((d) => {
        setCadernos(Array.isArray(d) ? d : []);
      })
      .catch(() => setCadernos([]))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="min-h-screen bg-page text-fg">
      <div className="border-b border-border/60 px-6 py-2 flex items-center gap-3 text-xs bg-page">
        <span className="text-fg-faint">Estudo</span>
        <span className="text-fg-faint">›</span>
        <span className="text-fg-muted">Planejamento</span>
      </div>

      <main className="max-w-3xl mx-auto px-6 py-6">
        <h1 className="text-xl font-semibold mb-1">Planejamento</h1>
        <p className="text-sm text-fg-muted mb-6">
          Selecione um caderno para gerar ou visualizar seu cronograma de estudo.
        </p>

        {loading && (
          <p className="text-sm text-fg-faint">Carregando cadernos…</p>
        )}

        {!loading && cadernos.length === 0 && (
          <p className="text-sm text-fg-faint italic">
            Nenhum caderno encontrado. Crie um caderno em{" "}
            <Link href="/q/filtrar" className="text-primary hover:underline">
              Filtrar Questões
            </Link>{" "}
            ou acesse um{" "}
            <Link href="/q/guias" className="text-primary hover:underline">
              Guia de Estudos
            </Link>
            .
          </p>
        )}

        <div className="grid gap-2">
          {cadernos.map((c) => (
            <a
              key={c.id}
              href={`/q/caderno/${c.id}/cronograma`}
              className="bg-surface border border-border/60 rounded-lg px-4 py-3 flex items-center justify-between hover:border-primary/40 transition"
            >
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-fg truncate">{c.nome}</div>
                {c.pasta && (
                  <div className="text-xs text-fg-faint truncate">{c.pasta}</div>
                )}
              </div>
              <span className="text-fg-faint text-xs shrink-0 ml-4">
                {c.total.toLocaleString("pt-BR")} questões · cronograma →
              </span>
            </a>
          ))}
        </div>
      </main>
    </div>
  );
}

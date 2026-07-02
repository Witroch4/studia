"use client";

import { useState } from "react";
import { PassoConcurso, type ConcursoCatalogoItem } from "./components/PassoConcurso";
import { PassoExtracao, type DadosExtracao } from "./components/PassoExtracao";
import { PassoCargo } from "./components/PassoCargo";

type Passo = "concurso" | "extracao" | "cargo";

const PASSOS: { key: Passo; label: string }[] = [
  { key: "concurso", label: "Concurso" },
  { key: "extracao", label: "Leitura do edital" },
  { key: "cargo", label: "Cargo" },
];

export default function NovoMapaPage() {
  const [passo, setPasso] = useState<Passo>("concurso");
  const [concurso, setConcurso] = useState<ConcursoCatalogoItem | null>(null);
  const [dadosExtracao, setDadosExtracao] = useState<DadosExtracao | null>(null);

  function handleSelecionarConcurso(c: ConcursoCatalogoItem) {
    setConcurso(c);
    setDadosExtracao(null);
    setPasso("extracao");
  }

  function handleExtracaoConcluida(dados: DadosExtracao) {
    setDadosExtracao(dados);
    setPasso("cargo");
  }

  function handleTrocarConcurso() {
    setConcurso(null);
    setDadosExtracao(null);
    setPasso("concurso");
  }

  const passoAtualIndex = PASSOS.findIndex((p) => p.key === passo);

  return (
    <div className="min-h-screen bg-page text-fg">
      <div className="max-w-3xl mx-auto p-6 space-y-6">
        <header>
          <h1 className="text-2xl font-bold text-fg-strong flex items-center gap-2">
            <span className="material-symbols-outlined text-primary">map</span>
            Criar Mapa da Aprovação
          </h1>
          <p className="text-sm text-fg-muted mt-1">
            Do edital à prova: cargos, matérias, prazos e questões da banca em um só plano.
          </p>
        </header>

        <ol className="flex items-center gap-2 text-xs">
          {PASSOS.map((p, i) => {
            const ativo = i === passoAtualIndex;
            const concluido = i < passoAtualIndex;
            return (
              <li key={p.key} className="flex items-center gap-2">
                <span
                  className={`flex items-center gap-1.5 rounded-full px-3 py-1.5 font-medium ${
                    ativo
                      ? "bg-primary text-on-primary"
                      : concluido
                      ? "bg-primary/15 text-primary"
                      : "bg-surface-2 text-fg-faint"
                  }`}
                >
                  {concluido ? (
                    <span className="material-symbols-outlined text-[14px]">check</span>
                  ) : (
                    <span>{i + 1}</span>
                  )}
                  {p.label}
                </span>
                {i < PASSOS.length - 1 && (
                  <span className="material-symbols-outlined text-[14px] text-fg-faint">
                    chevron_right
                  </span>
                )}
              </li>
            );
          })}
        </ol>

        {passo === "concurso" && <PassoConcurso onSelecionar={handleSelecionarConcurso} />}

        {passo === "extracao" && concurso && (
          <PassoExtracao
            concurso={concurso}
            onConcluido={handleExtracaoConcluida}
            onTrocarConcurso={handleTrocarConcurso}
          />
        )}

        {passo === "cargo" && concurso && dadosExtracao && (
          <PassoCargo
            concurso={concurso}
            dados={dadosExtracao}
            onTrocarConcurso={handleTrocarConcurso}
          />
        )}
      </div>
    </div>
  );
}

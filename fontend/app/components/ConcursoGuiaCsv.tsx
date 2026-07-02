"use client";

import { useState } from "react";

/**
 * Guia expandível do padrão de CSV aceito pela página de Concorrência.
 * Fechado por padrão; abre por ação do usuário (sem layout shift assíncrono).
 */

type Col = { nome: string; aliases?: string; desc: string };

const OBRIGATORIAS: Col[] = [
  { nome: "PONTOS", aliases: "TOTAL, NOTA, NOTA FINAL", desc: "Pontuação final do candidato (aceita vírgula ou ponto decimal)." },
  { nome: "AC", aliases: "AMPLA", desc: "Posição do candidato na lista de ampla concorrência (1, 2, 3…)." },
];

const OPCIONAIS: Col[] = [
  { nome: "CARGO", desc: "Nome do cargo — permite filtrar quando o CSV tem vários cargos." },
  { nome: "POLO", aliases: "UF, ESTADO", desc: "Estado/polo da vaga — habilita o recorte por estado." },
  { nome: "MACROPOLO", aliases: "REGIÃO", desc: "Região (SUDESTE, NORDESTE…) — habilita o recorte por região." },
  { nome: "INSCRIÇÃO", aliases: "INSC", desc: "Número de inscrição (aparece na lista de classificação)." },
  { nome: "D.NASCIMENTO", aliases: "NASCIMENTO", desc: "Data de nascimento (dd/mm/aaaa) — usada no desempate por idade." },
  { nome: "TOT.ESP.", aliases: "ESPECÍFICA", desc: "Pontos de conhecimento específico — necessário p/ critério padrão Petrobras." },
  { nome: "TOT.BAS.", aliases: "BÁSICOS", desc: "Pontos de conhecimentos básicos." },
  { nome: "L.PORT. / L.ING.", aliases: "PORTUGUÊS / INGLÊS", desc: "Notas de Português e Inglês — desempate do critério Petrobras." },
  { nome: "DISCURSIVA", aliases: "DISC", desc: "Nota da discursiva — primeiro desempate do critério de pontos." },
  { nome: "PCD, PN, PI, PQ", desc: "Posição do candidato em cada lista de cota (veja o destaque abaixo)." },
];

const EXEMPLO = `CARGO,POLO,MACROPOLO,INSCRIÇÃO,PONTOS,AC,PCD,PN,PI,PQ
ENGENHEIRO CIVIL,GO,CENTRO-OESTE,2500010699,66,1,,1,,
ENGENHEIRO CIVIL,RN,NORDESTE,2500278004,66,2,,,,
ENGENHEIRO CIVIL,SP,SUDESTE,2500312563,64,3,1,,,`;

export default function ConcursoGuiaCsv() {
  const [aberto, setAberto] = useState(false);

  return (
    <div className="border border-border-dark rounded-xl overflow-hidden bg-bg-dark/40">
      <button
        type="button"
        onClick={() => setAberto((a) => !a)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-colors cursor-pointer"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-fg-strong">
          <span className="material-symbols-outlined text-primary text-[20px]">help</span>
          Como preparar o CSV
        </span>
        <span className={`material-symbols-outlined text-fg-faint transition-transform ${aberto ? "rotate-180" : ""}`}>
          expand_more
        </span>
      </button>

      {aberto && (
        <div className="px-4 pb-5 pt-1 border-t border-border-dark space-y-5 text-sm text-fg-muted">
          <p>
            Use o resultado oficial do concurso (ou monte sua planilha) e salve como{" "}
            <strong className="text-fg">.csv</strong> — separador vírgula ou ponto-e-vírgula, os dois
            funcionam. A ordem das colunas não importa e os nomes aceitam variações (aliases abaixo).
          </p>

          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-primary mb-2">
              Colunas obrigatórias
            </p>
            <TabelaColunas cols={OBRIGATORIAS} obrigatoria />
          </div>

          <div className="rounded-lg border border-warning/30 bg-warning/10 px-4 py-3">
            <p className="flex items-start gap-2">
              <span className="material-symbols-outlined text-warning text-[18px] mt-0.5">priority_high</span>
              <span>
                <strong className="text-fg">AC, PCD, PN, PI e PQ não são &quot;sim/não&quot;</strong> — cada uma guarda a{" "}
                <strong className="text-fg">posição do candidato naquela lista</strong> (1º, 2º, 3º…).
                Célula <strong className="text-fg">vazia</strong> = o candidato não concorre àquela cota.
                É assim que o resultado oficial costuma vir publicado.
              </span>
            </p>
          </div>

          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-fg-faint mb-2">
              Colunas opcionais (habilitam recortes e critérios extras)
            </p>
            <TabelaColunas cols={OPCIONAIS} />
          </div>

          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-fg-faint mb-2">Exemplo</p>
            <pre className="cc-num text-[11px] leading-relaxed bg-bg-dark border border-border-dark rounded-lg p-3 overflow-x-auto text-fg">
              {EXEMPLO}
            </pre>
            <p className="text-[11px] text-fg-faint mt-2">
              Na 1ª linha do exemplo, o candidato é 1º na ampla (AC=1) e 1º na lista de pretos e pardos
              (PN=1); na 3ª, o candidato é 3º na ampla e 1º na lista PcD.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function TabelaColunas({ cols, obrigatoria = false }: { cols: Col[]; obrigatoria?: boolean }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="text-[10px] uppercase tracking-wider text-fg-faint border-b border-border-dark">
            <th className="text-left font-semibold py-2 pr-3 whitespace-nowrap">Coluna</th>
            <th className="text-left font-semibold py-2 pr-3 whitespace-nowrap">Também aceita</th>
            <th className="text-left font-semibold py-2">O que é</th>
          </tr>
        </thead>
        <tbody>
          {cols.map((c) => (
            <tr key={c.nome} className="border-b border-border-dark/50 align-top">
              <td className="py-2 pr-3 whitespace-nowrap">
                <code className={`cc-num font-bold px-1.5 py-0.5 rounded ${obrigatoria ? "bg-primary/15 text-primary" : "bg-white/5 text-fg"}`}>
                  {c.nome}
                </code>
              </td>
              <td className="py-2 pr-3 text-fg-faint whitespace-nowrap">{c.aliases || "—"}</td>
              <td className="py-2 text-fg-muted">{c.desc}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

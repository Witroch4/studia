"use client";

import { useState } from "react";

/**
 * Guia expandível do formato .md aceito pelo import de flashcards.
 * Mesmo padrão visual do ConcursoGuiaCsv (fechado por padrão; abre por
 * ação do usuário — sem layout shift assíncrono).
 */

type Tag = { nome: string; exemplo: string; desc: string };

const TAGS: Tag[] = [
  { nome: "<atencao>", exemplo: "<atencao>Título: texto</atencao>", desc: "Box vermelho de alerta — regras que derrubam candidato, pegadinhas de banca." },
  { nome: "<destaque>", exemplo: "<destaque>termo-chave</destaque>", desc: "Realce ciano inline — o termo que você precisa gravar." },
  { nome: "<resumo>", exemplo: "<resumo>$$F_s = 2{,}0$$</resumo>", desc: "Box ciano centralizado — ótimo para fórmulas e sínteses." },
];

const EXEMPLO = `Flashcard: Engenharia Civil: Fundações - NBR 6122
Frente: Qual o fator de segurança global mínimo para métodos semi-empíricos?
Verso:
A NBR 6122 exige <destaque>Fs mínimo</destaque> conforme o método:

<resumo>
$$F_s = 2{,}0$$ (semi-empírico sem prova de carga)
</resumo>

<atencao>Pegadinha: com prova de carga executada, o Fs pode cair para 1,6.</atencao>

Flashcard: Engenharia Civil: Outro Assunto
Frente: Próxima pergunta...
Verso:
Próxima resposta...`;

export default function FlashcardGuiaMd() {
  const [aberto, setAberto] = useState(false);
  const [copiado, setCopiado] = useState(false);

  const copiarExemplo = () => {
    navigator.clipboard.writeText(EXEMPLO).then(() => {
      setCopiado(true);
      setTimeout(() => setCopiado(false), 2000);
    });
  };

  return (
    <div className="border border-border-dark rounded-xl overflow-hidden bg-bg-dark/40">
      <button
        type="button"
        onClick={() => setAberto((a) => !a)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/5 transition-colors cursor-pointer"
      >
        <span className="flex items-center gap-2 text-sm font-semibold text-fg-strong">
          <span className="material-symbols-outlined text-primary text-[20px]">help</span>
          Como criar seus flashcards
        </span>
        <span className={`material-symbols-outlined text-fg-faint transition-transform ${aberto ? "rotate-180" : ""}`}>
          expand_more
        </span>
      </button>

      {aberto && (
        <div className="px-4 pb-5 pt-1 border-t border-border-dark space-y-5 text-sm text-fg-muted">
          <p>
            Cada cartão é um bloco de três partes. A primeira linha define o baralho
            (<strong className="text-fg">Tema</strong> vira o baralho, <strong className="text-fg">Assunto</strong> vira
            a etiqueta do cartão); depois vêm a pergunta e a resposta:
          </p>

          <pre className="cc-num text-[12px] leading-relaxed bg-bg-dark border border-border-dark rounded-lg p-3 overflow-x-auto text-fg">
{`Flashcard: Tema: Assunto
Frente: pergunta concisa (sem tags XML)
Verso:
resposta estruturada — aceita **markdown**, $LaTeX$ e as tags abaixo`}
          </pre>

          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-primary mb-2">
              Tags de destaque (só no Verso)
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wider text-fg-faint border-b border-border-dark">
                    <th className="text-left font-semibold py-2 pr-3 whitespace-nowrap">Tag</th>
                    <th className="text-left font-semibold py-2 pr-3 whitespace-nowrap">Exemplo</th>
                    <th className="text-left font-semibold py-2">Para que serve</th>
                  </tr>
                </thead>
                <tbody>
                  {TAGS.map((t) => (
                    <tr key={t.nome} className="border-b border-border-dark/50 align-top">
                      <td className="py-2 pr-3 whitespace-nowrap">
                        <code className="cc-num font-bold px-1.5 py-0.5 rounded bg-primary/15 text-primary">
                          {t.nome}
                        </code>
                      </td>
                      <td className="py-2 pr-3 text-fg-faint whitespace-nowrap">
                        <code className="cc-num">{t.exemplo}</code>
                      </td>
                      <td className="py-2 text-fg-muted">{t.desc}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          <div className="rounded-lg border border-warning/30 bg-warning/10 px-4 py-3">
            <p className="flex items-start gap-2">
              <span className="material-symbols-outlined text-warning text-[18px] mt-0.5">priority_high</span>
              <span>
                Repita o bloco <strong className="text-fg">Flashcard:</strong> para cada cartão — quantos quiser
                no mesmo arquivo. Cartões com o mesmo <strong className="text-fg">Tema</strong> caem no mesmo
                baralho, e <strong className="text-fg">reimportar o arquivo não duplica</strong> o que já existe.
              </span>
            </p>
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <p className="text-[11px] font-bold uppercase tracking-wider text-fg-faint">Exemplo completo</p>
              <button
                type="button"
                onClick={copiarExemplo}
                className="flex items-center gap-1 text-[11px] text-fg-muted hover:text-primary transition-colors"
              >
                <span className="material-symbols-outlined text-[14px]">
                  {copiado ? "check" : "content_copy"}
                </span>
                {copiado ? "Copiado!" : "Copiar exemplo"}
              </button>
            </div>
            <pre className="cc-num text-[11px] leading-relaxed bg-bg-dark border border-border-dark rounded-lg p-3 overflow-x-auto text-fg">
              {EXEMPLO}
            </pre>
            <p className="text-[11px] text-fg-faint mt-2">
              O formato é tolerante: <code className="cc-num">flashcard:</code> minúsculo,{" "}
              <code className="cc-num">**Frente:**</code> em negrito e arquivos salvos no Windows funcionam
              do mesmo jeito.
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

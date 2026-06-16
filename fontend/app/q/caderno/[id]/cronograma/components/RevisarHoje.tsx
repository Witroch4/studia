"use client";
import type { RevisaoItem } from "../api";
export function RevisarHoje({ itens }: { itens: RevisaoItem[] }) {
  if (!itens.length) return <p className="text-sm text-fg-faint">Nada para revisar hoje. 🎉</p>;
  return (
    <ul className="space-y-1 text-sm">
      {itens.map((i) => (
        <li key={`${i.questao_id}-${i.intervalo}`} className="flex justify-between bg-surface border border-border/60 rounded px-3 py-1.5">
          <a className="text-primary" href={`/q/questao/${i.questao_id}`}>Questão #{i.questao_id}</a>
          <span className="text-fg-faint">{i.intervalo} · vence {i.revisar_em.slice(5)}</span>
        </li>
      ))}
    </ul>
  );
}

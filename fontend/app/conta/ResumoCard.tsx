"use client";

import Link from "next/link";
import { useMeuPerfil } from "./usePerfil";
import { Skeleton } from "@/app/components/ds";

function Stat({ label, valor }: { label: string; valor: string | number }) {
  return (
    <div className="rounded-lg bg-bg-dark px-3 py-2.5 text-center">
      <div className="text-lg font-bold text-fg-strong">{valor}</div>
      <div className="text-[0.65rem] uppercase tracking-wide text-fg-faint">{label}</div>
    </div>
  );
}

export default function ResumoCard() {
  const { data, isPending } = useMeuPerfil();
  const r = data?.resumo;

  return (
    <section className="rounded-xl border border-border-dark bg-surface-dark p-6">
      <h2 className="flex items-center gap-2 text-base font-semibold text-fg-strong mb-4">
        <span className="material-symbols-outlined text-primary text-[20px]">military_tech</span>
        Resumo estatístico
      </h2>

      {isPending || !r ? (
        <div className="space-y-4">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      ) : (
        <div className="space-y-4">
          <div
            className="flex items-center justify-between rounded-lg bg-gradient-to-r from-primary/15 to-secondary/15 px-4 py-3"
            title="Pontuação final = pontos do fórum + metas ×10 + combos ×2 valem 20, ×3 valem 30 e ×4 valem 40"
          >
            <span className="text-sm font-medium text-fg">Pontuação final</span>
            <span className="text-2xl font-bold text-primary">{r.pontuacao.total}</span>
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Fórum" valor={r.pontuacao.forum} />
            <Stat label="Estudo" valor={r.pontuacao.estudo} />
            <Stat label="Comentários" valor={r.pontuacao.comentarios} />
          </div>
          <div className="grid grid-cols-4 gap-2">
            <Stat label="Metas batidas" valor={r.pontuacao.metas} />
            <Stat label="Combos ×2" valor={r.pontuacao.combos_x2} />
            <Stat label="Combos ×3" valor={r.pontuacao.combos_x3} />
            <Stat label="Combos ×4" valor={r.pontuacao.combos_x4} />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Resolvidas" valor={r.resolvidas} />
            <Stat label="Taxa de acerto" valor={`${r.taxa}%`} />
            <Stat label="Sequência (dias)" valor={r.streak_dias} />
          </div>
          <Link href="/painel" className="block text-sm text-primary hover:underline">
            Ver painel completo →
          </Link>
        </div>
      )}
    </section>
  );
}

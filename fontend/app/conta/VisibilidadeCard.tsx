"use client";

import { useAtualizarPerfil, useMeuPerfil } from "./usePerfil";
import { Skeleton } from "@/app/components/ds";

function Toggle({ label, desc, checked, onChange, disabled }: {
  label: string; desc: string; checked: boolean;
  onChange: (v: boolean) => void; disabled: boolean;
}) {
  return (
    <label className="flex items-start justify-between gap-4 cursor-pointer">
      <span>
        <span className="block text-sm font-medium text-fg-strong">{label}</span>
        <span className="block text-xs text-fg-faint">{desc}</span>
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        onClick={() => onChange(!checked)}
        className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${checked ? "bg-primary" : "bg-border-dark"} disabled:opacity-50`}
      >
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-transform ${checked ? "translate-x-[22px]" : "translate-x-0.5"}`} />
      </button>
    </label>
  );
}

export default function VisibilidadeCard() {
  const { data, isPending } = useMeuPerfil();
  const atualizar = useAtualizarPerfil();

  return (
    <section className="rounded-xl border border-border-dark bg-surface-dark p-6">
      <h2 className="flex items-center gap-2 text-base font-semibold text-fg-strong mb-4">
        <span className="material-symbols-outlined text-primary text-[20px]">visibility</span>
        Visibilidade do perfil
      </h2>
      {isPending || !data ? (
        <div className="space-y-4">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </div>
      ) : (
        <div className="space-y-4">
          <Toggle
            label="Perfil público"
            desc="Seu perfil fica acessível pelo apelido e o fórum linka para ele."
            checked={data.perfil_publico}
            disabled={atualizar.isPending}
            onChange={(v) => atualizar.mutate({ perfil_publico: v })}
          />
          <Toggle
            label="Mostrar estatísticas de estudo"
            desc="Questões resolvidas, taxa de acerto, metas e combos no perfil público."
            checked={data.mostrar_estatisticas}
            disabled={atualizar.isPending}
            onChange={(v) => atualizar.mutate({ mostrar_estatisticas: v })}
          />
          <Toggle
            label="Mostrar foto"
            desc="Sem a foto, o perfil e o fórum exibem só as iniciais."
            checked={data.mostrar_foto}
            disabled={atualizar.isPending}
            onChange={(v) => atualizar.mutate({ mostrar_foto: v })}
          />
        </div>
      )}
    </section>
  );
}

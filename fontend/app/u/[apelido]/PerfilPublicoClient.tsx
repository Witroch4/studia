"use client";

import Link from "next/link";
import { ApiError, apiUrl } from "@/lib/api";
import { Skeleton } from "@/app/components/ds";
import { usePerfilPublico } from "../../conta/usePerfil";

function Stat({ label, valor }: { label: string; valor: string | number }) {
  return (
    <div className="rounded-lg bg-surface-dark px-3 py-3 text-center">
      <div className="text-xl font-bold text-fg-strong">{valor}</div>
      <div className="text-[0.65rem] uppercase tracking-wide text-fg-faint">{label}</div>
    </div>
  );
}

function EstadoVazio({ icone, titulo, texto }: { icone: string; titulo: string; texto: string }) {
  return (
    <div className="flex flex-col items-center gap-2 rounded-xl border border-border-dark bg-surface-dark px-6 py-16 text-center">
      <span className="material-symbols-outlined text-[40px] text-fg-faint">{icone}</span>
      <h1 className="text-lg font-semibold text-fg-strong">{titulo}</h1>
      <p className="text-sm text-fg-faint">{texto}</p>
      <Link href="/" className="mt-2 text-sm text-primary hover:underline">Voltar ao início</Link>
    </div>
  );
}

export default function PerfilPublicoClient({ apelido }: { apelido: string }) {
  const { data, isPending, error } = usePerfilPublico(apelido);

  if (isPending) {
    return (
      <div className="px-6 py-8 md:px-10 max-w-3xl w-full mx-auto space-y-6">
        <div className="flex items-center gap-4">
          <Skeleton className="h-20 w-20 rounded-full" />
          <div className="space-y-2">
            <Skeleton className="h-6 w-48" />
            <Skeleton className="h-4 w-32" />
          </div>
        </div>
        <Skeleton className="h-16 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }

  if (error || !data) {
    const privado =
      error instanceof ApiError &&
      typeof (error.data as { detail?: { privado?: boolean } })?.detail === "object" &&
      (error.data as { detail?: { privado?: boolean } }).detail?.privado === true;
    return (
      <div className="px-6 py-8 md:px-10 max-w-3xl w-full mx-auto">
        {privado ? (
          <EstadoVazio icone="lock" titulo="Perfil privado"
            texto="Este usuário optou por não exibir o perfil publicamente." />
        ) : (
          <EstadoVazio icone="person_off" titulo="Perfil não encontrado"
            texto="Não existe nenhum usuário com este apelido." />
        )}
      </div>
    );
  }

  const e = data.estatisticas;
  return (
    <div className="px-6 py-8 md:px-10 max-w-3xl w-full mx-auto space-y-6">
      <div className="flex items-center gap-4">
        <div className="h-20 w-20 rounded-full bg-gradient-to-tr from-primary to-secondary p-[2px] shrink-0">
          {data.avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={apiUrl(data.avatar_url)} alt={`Foto de ${data.apelido}`}
              className="rounded-full h-full w-full object-cover" />
          ) : (
            <div className="rounded-full h-full w-full bg-surface-dark flex items-center justify-center">
              <span className="text-xl font-bold text-fg-strong">
                {data.apelido.slice(0, 2).toUpperCase()}
              </span>
            </div>
          )}
        </div>
        <div>
          <h1 className="text-2xl font-bold text-fg-strong">@{data.apelido}</h1>
          {data.membro_desde && (
            <p className="text-sm text-fg-faint">
              Membro desde {new Date(data.membro_desde).toLocaleDateString("pt-BR", { month: "long", year: "numeric" })}
            </p>
          )}
        </div>
        {data.badge && (
          <span className="ml-auto inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-bold uppercase tracking-wide text-secondary bg-secondary/10">
            <span className="material-symbols-outlined text-[14px]">
              {data.badge === "admin" ? "shield_person" : "school"}
            </span>
            {data.badge}
          </span>
        )}
      </div>

      <div
        className="flex items-center justify-between rounded-xl border border-border-dark bg-gradient-to-r from-primary/15 to-secondary/15 px-5 py-4"
        title="Pontuação final = pontos do fórum + metas ×10 + combos ×2 valem 20, ×3 valem 30 e ×4 valem 40"
      >
        <span className="text-sm font-medium text-fg">Pontuação final</span>
        <span className="text-3xl font-bold text-primary">{data.pontuacao.total}</span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <Stat label="Pontos no fórum" valor={data.pontuacao.forum} />
        <Stat label="Comentários" valor={data.pontuacao.comentarios} />
      </div>

      {e && (
        <>
          <div className="grid grid-cols-4 gap-2">
            <Stat label="Metas batidas" valor={e.metas} />
            <Stat label="Combos ×2" valor={e.combos_x2} />
            <Stat label="Combos ×3" valor={e.combos_x3} />
            <Stat label="Combos ×4" valor={e.combos_x4} />
          </div>
          <div className="grid grid-cols-3 gap-2">
            <Stat label="Resolvidas" valor={e.resolvidas} />
            <Stat label="Taxa de acerto" valor={`${e.taxa}%`} />
            <Stat label="Sequência (dias)" valor={e.streak_dias} />
          </div>
        </>
      )}
    </div>
  );
}

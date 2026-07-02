"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiPost, ApiError } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import type { ConcursoCatalogoItem } from "./PassoConcurso";
import type { CargoEdital, DadosExtracao } from "./PassoExtracao";

// ─── Tipos ───────────────────────────────────────────────

interface CriarMapaResponse {
  id: number;
  redirect: string;
  cadernos_criados: number;
  total_questoes: number;
}

interface MapaDuplicadoDetail {
  msg: string;
  id: number;
}

// ─── Helpers ─────────────────────────────────────────────

function formatarData(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("pt-BR");
}

function isMapaDuplicado(data: unknown): data is { detail: MapaDuplicadoDetail } {
  const d = data as { detail?: unknown } | null;
  return !!d && typeof d.detail === "object" && d.detail !== null && "id" in (d.detail as object);
}

// ─── Componente ──────────────────────────────────────────

export function PassoCargo({
  concurso,
  dados,
  onTrocarConcurso,
}: {
  concurso: ConcursoCatalogoItem;
  dados: DadosExtracao;
  onTrocarConcurso: () => void;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [cargoSelecionado, setCargoSelecionado] = useState<CargoEdital | null>(null);

  const criarMapa = useMutation<CriarMapaResponse, ApiError, void>({
    mutationFn: () => {
      if (!cargoSelecionado) throw new Error("Selecione um cargo primeiro");
      return apiPost<CriarMapaResponse>("/api/q/mapas", {
        concurso_id: concurso.id,
        cargo_nome: cargoSelecionado.nome,
      });
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: qk.mapas() });
      toast.success(
        `Mapa criado! ${res.cadernos_criados} caderno(s) e ${res.total_questoes} questão(ões) prontas.`
      );
      router.push(res.redirect);
    },
  });

  const cargos = dados.cargos ?? [];
  const mapaDuplicado =
    criarMapa.isError && criarMapa.error.status === 409 && isMapaDuplicado(criarMapa.error.data)
      ? (criarMapa.error.data as { detail: MapaDuplicadoDetail }).detail
      : null;
  const ehPaywall = criarMapa.isError && criarMapa.error.status === 403;

  return (
    <section className="space-y-4">
      <button
        type="button"
        onClick={onTrocarConcurso}
        className="text-xs text-fg-faint hover:text-primary"
      >
        ‹ Trocar concurso
      </button>

      <div>
        <h2 className="text-lg font-semibold text-fg-strong">3. Escolha o cargo</h2>
        <p className="text-sm text-fg-muted mt-1">
          {cargos.length === 0
            ? "A IA não encontrou cargos estruturados neste edital."
            : `Li o edital e encontrei ${cargos.length} cargo${cargos.length === 1 ? "" : "s"}.`}
        </p>
      </div>

      {cargos.length === 0 && (
        <div className="rounded-xl border border-border bg-surface p-8 text-center text-sm text-fg-muted">
          Tente escolher outro concurso ou fale com o suporte.
        </div>
      )}

      {cargos.length > 0 && !cargoSelecionado && (
        <div className="grid gap-3 sm:grid-cols-2">
          {cargos.map((c) => (
            <button
              key={c.nome}
              type="button"
              onClick={() => setCargoSelecionado(c)}
              className="text-left rounded-xl border border-border bg-surface p-4 space-y-1.5 transition hover:border-primary/50 hover:bg-primary/5"
            >
              <h3 className="font-medium text-fg-strong leading-snug">{c.nome || "Cargo sem nome"}</h3>
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-fg-muted">
                {c.vagas && <span>Vagas: {c.vagas}</span>}
                {c.salario && <span>Salário: {c.salario}</span>}
                {c.escolaridade && <span>{c.escolaridade}</span>}
              </div>
              <p className="text-xs text-fg-faint">
                {c.conteudo_programatico.length} matéria(s) no programa
              </p>
            </button>
          ))}
        </div>
      )}

      {cargoSelecionado && (
        <div className="space-y-4">
          <div className="rounded-xl border border-primary/40 bg-primary/5 p-4 flex items-start justify-between gap-3">
            <div>
              <h3 className="font-semibold text-fg-strong">{cargoSelecionado.nome}</h3>
              <div className="flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-fg-muted mt-1">
                {cargoSelecionado.vagas && <span>Vagas: {cargoSelecionado.vagas}</span>}
                {cargoSelecionado.salario && <span>Salário: {cargoSelecionado.salario}</span>}
                {cargoSelecionado.escolaridade && <span>{cargoSelecionado.escolaridade}</span>}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setCargoSelecionado(null)}
              className="text-xs text-fg-faint hover:text-primary shrink-0"
            >
              Trocar cargo
            </button>
          </div>

          {cargoSelecionado.conteudo_programatico.length > 0 && (
            <div className="rounded-xl border border-border bg-surface p-4">
              <h4 className="text-sm font-semibold text-fg-strong mb-2">Matérias do programa</h4>
              <ul className="space-y-1.5 text-sm text-fg-muted">
                {cargoSelecionado.conteudo_programatico.map((m, i) => (
                  <li key={`${m.materia}-${i}`}>
                    <span className="text-fg font-medium">{m.materia || "Matéria sem nome"}</span>
                    {m.assuntos.length > 0 && (
                      <span className="text-fg-faint"> — {m.assuntos.length} assunto(s)</span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {dados.eventos.length > 0 && (
            <div className="rounded-xl border border-border bg-surface p-4">
              <h4 className="text-sm font-semibold text-fg-strong mb-2">Datas importantes</h4>
              <ul className="space-y-1.5 text-sm text-fg-muted">
                {dados.eventos.map((e, i) => (
                  <li key={`${e.titulo}-${i}`} className="flex items-center justify-between gap-3">
                    <span>{e.titulo || "Evento"}</span>
                    <span className="text-fg-faint shrink-0">
                      {formatarData(e.data_inicio)}
                      {e.data_fim && e.data_fim !== e.data_inicio ? ` – ${formatarData(e.data_fim)}` : ""}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {ehPaywall && (
            <div className="rounded-xl border border-warning/40 bg-warning/10 px-4 py-4 text-sm text-fg space-y-1">
              <p className="font-medium">O Mapa da Aprovação é um recurso PRO.</p>
              <Link href="/assinar" className="font-semibold text-primary hover:underline">
                Assine para desbloquear →
              </Link>
            </div>
          )}

          {mapaDuplicado && (
            <div className="rounded-xl border border-border bg-surface-2 px-4 py-4 text-sm text-fg space-y-1">
              <p>Você já tem um Mapa para este cargo.</p>
              <Link href={`/q/mapa/${mapaDuplicado.id}`} className="font-semibold text-primary hover:underline">
                Abrir o Mapa que você já tem →
              </Link>
            </div>
          )}

          {criarMapa.isError && !ehPaywall && !mapaDuplicado && (
            <div className="rounded-xl border border-error/40 bg-error/10 px-4 py-3 text-sm text-error">
              Não foi possível criar o Mapa. Tente de novo.
            </div>
          )}

          <button
            type="button"
            onClick={() => criarMapa.mutate()}
            disabled={criarMapa.isPending}
            className="inline-flex items-center gap-2 rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-on-primary transition hover:bg-primary-600 disabled:opacity-60"
          >
            <span className={`material-symbols-outlined text-[18px] ${criarMapa.isPending ? "animate-spin" : ""}`}>
              {criarMapa.isPending ? "progress_activity" : "map"}
            </span>
            {criarMapa.isPending ? "Montando seu Mapa…" : "Criar meu Mapa"}
          </button>
        </div>
      )}
    </section>
  );
}

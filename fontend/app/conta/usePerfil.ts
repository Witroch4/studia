"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

export type PerfilResumo = {
  pontuacao: {
    total: number; forum: number; estudo: number;
    metas: number; combos_x2: number; combos_x3: number; combos_x4: number;
    comentarios: number;
  };
  resolvidas: number;
  acertos: number;
  taxa: number;
  streak_dias: number;
};

export type MeuPerfil = {
  apelido: string | null;
  avatar_url: string | null;
  perfil_publico: boolean;
  mostrar_estatisticas: boolean;
  mostrar_foto: boolean;
  resumo: PerfilResumo;
};

export type PerfilPublico = {
  apelido: string;
  avatar_url: string | null;
  membro_desde: string | null;
  badge: "professor" | "admin" | null;
  pontuacao: { total: number; forum: number; comentarios: number };
  estatisticas: {
    resolvidas: number; acertos: number; taxa: number; streak_dias: number;
    estudo: number; metas: number; combos_x2: number; combos_x3: number; combos_x4: number;
  } | null;
};

export function useMeuPerfil() {
  return useQuery({
    queryKey: qk.perfil(),
    queryFn: () => apiJson<MeuPerfil>("/api/q/perfil"),
  });
}

export type PatchPerfil = Partial<{
  apelido: string;
  perfil_publico: boolean;
  mostrar_estatisticas: boolean;
  mostrar_foto: boolean;
}>;

export function useAtualizarPerfil() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PatchPerfil) =>
      apiJson<{ ok: boolean; apelido: string | null }>("/api/q/perfil", {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.perfil() }),
  });
}

export function useSubirAvatar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (file: File) => {
      const form = new FormData();
      form.append("file", file);
      const res = await apiFetch("/api/q/perfil/avatar", { method: "POST", body: form });
      if (!res.ok) {
        const data = await res.json().catch(() => null);
        throw new Error(
          (data && typeof data.detail === "string" && data.detail) || "Erro ao enviar a foto."
        );
      }
      return res.json() as Promise<{ avatar_url: string }>;
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.perfil() }),
  });
}

export function useRemoverAvatar() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => apiJson<{ ok: boolean }>("/api/q/perfil/avatar", { method: "DELETE" }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.perfil() }),
  });
}

export function usePerfilPublico(apelido: string) {
  return useQuery({
    queryKey: qk.perfilPublico(apelido),
    queryFn: () => apiJson<PerfilPublico>(`/api/q/perfil/u/${encodeURIComponent(apelido)}`),
    retry: false, // 404 (inexistente/privado) não deve re-tentar
  });
}

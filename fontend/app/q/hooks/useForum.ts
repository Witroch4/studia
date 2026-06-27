"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, apiJson, apiPost, API_BASE } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

export type Quadro = "alunos" | "professores";

export interface Comentario {
  id: number;
  parent_id: number | null;
  origem: "studia" | "tc";
  eh_professor: boolean;
  display_name: string;
  autor_inicial: string;
  texto_md: string | null;
  score: number;
  meu_voto: -1 | 0 | 1;
  criado_em: string | null;
  editado: boolean;
  removido: boolean;
  posso_editar: boolean;
  posso_excluir: boolean;
  respostas: Comentario[];
}

export interface ForumData {
  total: number;
  comentarios: Comentario[];
  tc_importado: boolean;
}

export function useForum(
  questaoId: number, quadro: Quadro, ordenar: "recentes" | "pontos", enabled = true,
) {
  return useQuery<ForumData>({
    queryKey: qk.forum(questaoId, quadro, ordenar),
    queryFn: () => apiJson(`/api/q/questoes/${questaoId}/forum?quadro=${quadro}&ordenar=${ordenar}`),
    enabled,
  });
}

function useInvalidarForum(questaoId: number, quadro: Quadro) {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: ["q", "forum", String(questaoId), quadro] });
}

export function useCriarComentario(questaoId: number, quadro: Quadro) {
  const invalidar = useInvalidarForum(questaoId, quadro);
  return useMutation({
    mutationFn: (body: { texto_md: string; parent_id?: number | null }) =>
      apiPost<Comentario>(`/api/q/questoes/${questaoId}/forum`, { ...body, quadro }),
    onSuccess: invalidar,
  });
}

export function useImportarComentariosTc(questaoId: number, quadro: Quadro) {
  const invalidar = useInvalidarForum(questaoId, quadro);
  return useMutation({
    mutationFn: () =>
      apiPost<{ importados: number; count: number; ja_importado: boolean }>(
        `/api/q/questoes/${questaoId}/importar-comentarios-tc?quadro=${quadro}`, {}),
    onSuccess: invalidar,
  });
}

export function useEditarComentario(questaoId: number, quadro: Quadro) {
  const invalidar = useInvalidarForum(questaoId, quadro);
  return useMutation({
    mutationFn: ({ id, texto_md }: { id: number; texto_md: string }) =>
      apiJson<Comentario>(`/api/q/forum/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ texto_md }),
      }),
    onSuccess: invalidar,
  });
}

export function useExcluirComentario(questaoId: number, quadro: Quadro) {
  const invalidar = useInvalidarForum(questaoId, quadro);
  return useMutation({
    mutationFn: (id: number) => apiJson(`/api/q/forum/${id}`, { method: "DELETE" }),
    onSuccess: invalidar,
  });
}

export function useVotar(questaoId: number, quadro: Quadro, ordenar: "recentes" | "pontos") {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, valor }: { id: number; valor: -1 | 0 | 1 }) =>
      apiPost<{ score: number; meu_voto: -1 | 0 | 1 }>(`/api/q/forum/${id}/voto`, { valor }),
    onMutate: async ({ id, valor }) => {
      const key = qk.forum(questaoId, quadro, ordenar);
      await qc.cancelQueries({ queryKey: ["q", "forum", String(questaoId), quadro] });
      const anterior = qc.getQueryData<ForumData>(key);
      if (anterior) {
        const aplica = (c: Comentario): Comentario => {
          if (c.id === id) {
            const delta = valor - c.meu_voto;
            return { ...c, meu_voto: valor, score: c.score + delta };
          }
          return { ...c, respostas: c.respostas.map(aplica) };
        };
        qc.setQueryData<ForumData>(key, { ...anterior, comentarios: anterior.comentarios.map(aplica) });
      }
      return { anterior, key };
    },
    onError: (_e, _v, ctx) => {
      if (ctx?.anterior) qc.setQueryData(ctx.key, ctx.anterior);
    },
    onSuccess: (data, { id }) => {
      const key = qk.forum(questaoId, quadro, ordenar);
      const atual = qc.getQueryData<ForumData>(key);
      if (!atual) return;
      const aplica = (c: Comentario): Comentario =>
        c.id === id
          ? { ...c, score: data.score, meu_voto: data.meu_voto }
          : { ...c, respostas: c.respostas.map(aplica) };
      qc.setQueryData<ForumData>(key, { ...atual, comentarios: atual.comentarios.map(aplica) });
    },
  });
}

export async function uploadImagemForum(file: File): Promise<string> {
  const fd = new FormData();
  fd.append("file", file);
  const res = await apiFetch("/api/q/forum/upload", { method: "POST", body: fd });
  if (!res.ok) throw new Error("falha no upload");
  const { url } = (await res.json()) as { url: string };
  return url.startsWith("http") ? url : `${API_BASE}${url}`;
}

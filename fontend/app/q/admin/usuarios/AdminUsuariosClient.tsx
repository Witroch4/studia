"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useSession } from "@/lib/auth-client";
import { apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";

interface UsuarioAdmin {
  id: string;
  email: string;
  name: string;
  role: "user" | "professor" | "admin";
  banned: boolean;
  created_at: string | null;
}
interface ListaUsuarios {
  usuarios: UsuarioAdmin[];
  page: number;
  tem_mais: boolean;
}

const ROLES: UsuarioAdmin["role"][] = ["user", "professor", "admin"];

export default function AdminUsuariosClient() {
  const router = useRouter();
  const { data: sessao, isPending: carregandoSessao } = useSession();
  const isAdmin = (sessao?.user as { role?: string } | undefined)?.role === "admin";

  const [busca, setBusca] = useState("");
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const qc = useQueryClient();

  // Redireciona não-admin assim que a sessão resolve.
  useEffect(() => {
    if (!carregandoSessao && !isAdmin) router.replace("/q");
  }, [carregandoSessao, isAdmin, router]);

  // Debounce simples da busca.
  useEffect(() => {
    const t = setTimeout(() => { setQ(busca); setPage(1); }, 300);
    return () => clearTimeout(t);
  }, [busca]);

  const { data, isPending } = useQuery<ListaUsuarios>({
    queryKey: qk.adminUsuarios(q, page),
    queryFn: () => apiJson(`/api/q/admin/usuarios?q=${encodeURIComponent(q)}&page=${page}`),
    enabled: isAdmin,
  });

  const trocarRole = useMutation({
    mutationFn: ({ uid, role }: { uid: string; role: string }) =>
      apiJson(`/api/q/admin/usuarios/${uid}/role`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ role }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin", "usuarios"] }),
  });

  if (carregandoSessao || !isAdmin) {
    return <div className="p-8 text-fg-muted">Carregando…</div>;
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="mb-4 text-xl font-bold text-fg-strong">Usuários e papéis</h1>
      <input
        value={busca}
        onChange={(e) => setBusca(e.target.value)}
        placeholder="Buscar por nome ou e-mail…"
        className="mb-4 w-full rounded-lg border border-border-dark bg-bg-dark px-3 py-2 text-sm text-fg-strong outline-none focus:border-primary"
      />

      {trocarRole.isError && (
        <p className="mb-3 text-sm text-error">
          {(trocarRole.error as Error)?.message || "Erro ao trocar papel."}
        </p>
      )}

      <div className="overflow-hidden rounded-lg border border-border">
        <table className="w-full text-sm">
          <thead className="bg-surface-2 text-left text-fg-faint">
            <tr>
              <th className="px-3 py-2">Nome</th>
              <th className="px-3 py-2">E-mail</th>
              <th className="px-3 py-2">Papel</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/50">
            {isPending && (
              <tr><td colSpan={3} className="px-3 py-4 text-fg-faint">Carregando…</td></tr>
            )}
            {data?.usuarios.map((u) => (
              <tr key={u.id}>
                <td className="px-3 py-2 text-fg">{u.name}</td>
                <td className="px-3 py-2 text-fg-faint">{u.email}</td>
                <td className="px-3 py-2">
                  <select
                    value={u.role}
                    disabled={trocarRole.isPending}
                    onChange={(e) => trocarRole.mutate({ uid: u.id, role: e.target.value })}
                    className="rounded border border-border-dark bg-bg-dark px-2 py-1 text-fg-strong outline-none focus:border-primary"
                  >
                    {ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
                  </select>
                </td>
              </tr>
            ))}
            {data && data.usuarios.length === 0 && (
              <tr><td colSpan={3} className="px-3 py-4 text-fg-faint">Nenhum usuário encontrado.</td></tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4 flex items-center justify-between text-sm text-fg-faint">
        <button type="button" disabled={page <= 1} onClick={() => setPage((p) => Math.max(1, p - 1))}
          className="rounded border border-border px-3 py-1 disabled:opacity-40">← Anterior</button>
        <span>Página {data?.page ?? page}</span>
        <button type="button" disabled={!data?.tem_mais} onClick={() => setPage((p) => p + 1)}
          className="rounded border border-border px-3 py-1 disabled:opacity-40">Próxima →</button>
      </div>
    </div>
  );
}

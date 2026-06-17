"use client";

import { useState, useEffect, useMemo } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { authClient } from "@/lib/auth-client";
import { apiJson, apiFetch } from "@/lib/api";
import { useQuery } from "@tanstack/react-query";
import { qk } from "@/lib/queryKeys";

interface CadernoItem {
  id: number;
  nome: string;
  total: number;
  tc_caderno_id: number | null;
  em_guia: boolean;
}
interface PastaGrupo {
  nome: string;
  cadernos: CadernoItem[];
}
interface UsuarioGrupo {
  uid: string | null;
  nome: string;
  email: string;
  total_cadernos: number;
  pastas: PastaGrupo[];
}
interface Resp {
  usuarios: UsuarioGrupo[];
}

export default function PastasUsuariosPage() {
  const router = useRouter();
  const [isAdmin, setIsAdmin] = useState<boolean | null>(null);
  const [busca, setBusca] = useState("");
  const [abertos, setAbertos] = useState<Record<string, boolean>>({});
  const [selecionados, setSelecionados] = useState<CadernoItem[]>([]);
  const [nome, setNome] = useState("");
  const [banca, setBanca] = useState("");
  const [proOnly, setProOnly] = useState(false);
  const [criando, setCriando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [dragIdx, setDragIdx] = useState<number | null>(null);

  useEffect(() => {
    authClient
      .getSession()
      .then((res) => {
        const role = (res?.data?.user as { role?: string } | undefined)?.role;
        setIsAdmin(role === "admin");
      })
      .catch(() => setIsAdmin(false));
  }, []);

  const { data, isPending, error } = useQuery<Resp>({
    queryKey: qk.guiasUsuariosPastas(),
    queryFn: () => apiJson<Resp>("/api/q/guias/usuarios-pastas"),
    enabled: isAdmin === true,
  });

  const termo = busca.trim().toLowerCase();
  const usuariosFiltrados = useMemo(() => {
    const us = data?.usuarios ?? [];
    if (!termo) return us;
    return us
      .map((u) => {
        const matchUser = u.nome.toLowerCase().includes(termo) || u.email.toLowerCase().includes(termo);
        const pastas = u.pastas
          .map((p) => ({
            ...p,
            cadernos: matchUser ? p.cadernos : p.cadernos.filter((c) => c.nome.toLowerCase().includes(termo) || p.nome.toLowerCase().includes(termo)),
          }))
          .filter((p) => p.cadernos.length > 0);
        return { ...u, pastas };
      })
      .filter((u) => u.pastas.length > 0);
  }, [data, termo]);

  const selIds = useMemo(() => new Set(selecionados.map((c) => c.id)), [selecionados]);

  function toggle(c: CadernoItem) {
    setSelecionados((prev) =>
      prev.some((x) => x.id === c.id) ? prev.filter((x) => x.id !== c.id) : [...prev, c]
    );
  }

  function moverPara(from: number, to: number) {
    setSelecionados((prev) => {
      if (to < 0 || to >= prev.length || from === to) return prev;
      const arr = [...prev];
      const [item] = arr.splice(from, 1);
      arr.splice(to, 0, item);
      return arr;
    });
  }

  async function gerarGuia() {
    const n = nome.trim();
    if (!n) {
      setMsg("Dê um nome ao guia.");
      return;
    }
    if (selecionados.length === 0) {
      setMsg("Selecione ao menos um caderno.");
      return;
    }
    setCriando(true);
    setMsg(null);
    try {
      const r = await apiFetch("/api/q/guias/manual", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nome: n,
          banca: banca.trim() || null,
          pro_only: proOnly,
          caderno_ids: selecionados.map((c) => c.id),
        }),
      });
      const d = await r.json();
      if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
      router.push(`/q/guias/${d.id}`);
    } catch (e) {
      setMsg((e as Error).message);
      setCriando(false);
    }
  }

  if (isAdmin === false) {
    return <div className="p-8 text-fg-muted">Acesso restrito a administradores.</div>;
  }

  const totalQuestoes = selecionados.reduce((s, c) => s + (c.total || 0), 0);

  return (
    <div className="min-h-screen bg-page text-fg">
      <header className="border-b border-border px-6 py-5">
        <Link href="/q/guias" className="text-xs text-fg-faint hover:text-primary">
          ← Guias
        </Link>
        <h1 className="text-2xl font-semibold flex items-center gap-2 mt-2">
          <span className="material-symbols-outlined text-primary text-3xl">folder_shared</span>
          Pastas de usuários
        </h1>
        <p className="text-sm text-fg-faint mt-1">
          Monte um guia selecionando cadernos de qualquer usuário (ou do catálogo) e definindo a ordem de estudo.
        </p>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-8 grid grid-cols-1 lg:grid-cols-[1fr_22rem] gap-6">
        {/* Origem: usuários → pastas → cadernos */}
        <section className="space-y-3">
          <div className="relative">
            <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-faint text-[18px] pointer-events-none">
              search
            </span>
            <input
              type="text"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              placeholder="Buscar por usuário, pasta ou caderno…"
              className="w-full pl-9 pr-3 py-2 bg-surface-2 border border-border rounded text-sm focus:outline-none focus:border-primary"
            />
          </div>

          {error && (
            <div className="bg-error/10 border border-error/40 rounded p-3 text-sm">
              <strong className="text-error">Falha:</strong> {(error as Error).message}
            </div>
          )}
          {isPending && <div className="text-sm text-fg-faint">Carregando cadernos…</div>}
          {!isPending && usuariosFiltrados.length === 0 && (
            <div className="text-sm text-fg-faint border border-dashed border-border rounded-lg p-8 text-center">
              Nenhum caderno encontrado.
            </div>
          )}

          {usuariosFiltrados.map((u) => {
            const key = u.uid ?? "__catalogo__";
            const aberto = abertos[key] ?? (termo.length > 0);
            return (
              <div key={key} className="rounded-lg border border-border bg-surface">
                <button
                  onClick={() => setAbertos((p) => ({ ...p, [key]: !aberto }))}
                  className="w-full flex items-center justify-between px-4 py-3 text-left"
                >
                  <span className="flex items-center gap-2 min-w-0">
                    <span className="material-symbols-outlined text-fg-faint text-[18px]">
                      {aberto ? "expand_more" : "chevron_right"}
                    </span>
                    <span className="min-w-0">
                      <span className="font-medium text-fg-strong">{u.nome}</span>
                      {u.email && <span className="text-xs text-fg-faint ml-2">{u.email}</span>}
                    </span>
                  </span>
                  <span className="text-xs text-fg-faint shrink-0">{u.total_cadernos} cadernos</span>
                </button>
                {aberto && (
                  <div className="px-4 pb-3 space-y-3">
                    {u.pastas.map((p) => (
                      <div key={p.nome}>
                        <div className="text-xs uppercase tracking-wide text-fg-faint mb-1 flex items-center gap-1">
                          <span className="material-symbols-outlined text-[14px]">folder</span>
                          {p.nome}
                        </div>
                        <div className="space-y-1">
                          {p.cadernos.map((c) => {
                            const sel = selIds.has(c.id);
                            return (
                              <label
                                key={c.id}
                                className={`flex items-center gap-2 px-2 py-1.5 rounded cursor-pointer text-sm hover:bg-fg-strong/5 ${sel ? "bg-primary/10" : ""}`}
                              >
                                <input
                                  type="checkbox"
                                  checked={sel}
                                  onChange={() => toggle(c)}
                                  className="accent-primary"
                                />
                                <span className="flex-1 min-w-0 truncate text-fg">{c.nome}</span>
                                <span className="text-xs text-fg-faint shrink-0">{c.total.toLocaleString("pt-BR")} q</span>
                                {c.em_guia && (
                                  <span className="text-[10px] uppercase text-fg-faint border border-border rounded px-1 shrink-0" title="Já está em algum guia">
                                    em guia
                                  </span>
                                )}
                              </label>
                            );
                          })}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </section>

        {/* Builder: selecionados + metadados */}
        <aside className="lg:sticky lg:top-6 self-start space-y-3 rounded-xl border border-border bg-surface p-4 h-fit">
          <h2 className="text-sm font-semibold text-fg-strong">Novo guia</h2>
          <input
            type="text"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            placeholder="Nome do guia *"
            className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-sm focus:outline-none focus:border-primary"
          />
          <input
            type="text"
            value={banca}
            onChange={(e) => setBanca(e.target.value)}
            placeholder="Banca (opcional)"
            className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-sm focus:outline-none focus:border-primary"
          />
          <label className="flex items-center justify-between gap-2 text-sm px-1 py-1">
            <span className="flex items-center gap-1.5">
              <span className="material-symbols-outlined text-warning text-[18px]">workspace_premium</span>
              PRO only
            </span>
            <button
              type="button"
              role="switch"
              aria-checked={proOnly}
              onClick={() => setProOnly((v) => !v)}
              className={`relative h-6 w-11 rounded-full transition-colors ${proOnly ? "bg-primary" : "bg-surface-2 border border-border"}`}
            >
              <span className={`absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform ${proOnly ? "translate-x-5" : ""}`} />
            </button>
          </label>

          <div className="border-t border-border pt-3">
            <div className="text-xs text-fg-muted mb-2">
              {selecionados.length} matéria(s) · {totalQuestoes.toLocaleString("pt-BR")} questões
            </div>
            {selecionados.length === 0 ? (
              <div className="text-xs text-fg-faint border border-dashed border-border rounded p-4 text-center">
                Marque cadernos à esquerda. Arraste aqui para ordenar.
              </div>
            ) : (
              <ul className="space-y-1">
                {selecionados.map((c, i) => (
                  <li
                    key={c.id}
                    draggable
                    onDragStart={() => setDragIdx(i)}
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={() => {
                      if (dragIdx !== null) moverPara(dragIdx, i);
                      setDragIdx(null);
                    }}
                    className="flex items-center gap-1.5 px-2 py-1.5 rounded bg-surface-2 text-sm cursor-grab active:cursor-grabbing"
                  >
                    <span className="material-symbols-outlined text-fg-faint text-[16px]">drag_indicator</span>
                    <span className="text-fg-faint text-xs w-4 shrink-0">{i + 1}</span>
                    <span className="flex-1 min-w-0 truncate">{c.nome}</span>
                    <button
                      onClick={() => toggle(c)}
                      title="Remover"
                      className="text-fg-faint hover:text-error shrink-0"
                    >
                      <span className="material-symbols-outlined text-[16px]">close</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          {msg && <div className="text-sm text-error">{msg}</div>}
          <button
            onClick={() => void gerarGuia()}
            disabled={criando || selecionados.length === 0 || !nome.trim()}
            className="w-full text-sm bg-primary hover:bg-primary-600 disabled:bg-surface-2 disabled:text-fg-faint text-on-primary px-4 py-2 rounded font-semibold"
          >
            {criando ? "Gerando…" : "Gerar guia"}
          </button>
        </aside>
      </main>
    </div>
  );
}

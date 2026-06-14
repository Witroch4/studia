"use client";

import Link from "next/link";
import { useState, useEffect } from "react";
import { apiFetch } from "@/lib/api";

const DISC_COLORS = [
  { iconBg: "bg-cyan-500/10", iconColor: "text-cyan-500" },
  { iconBg: "bg-orange-500/10", iconColor: "text-orange-500" },
  { iconBg: "bg-blue-500/10", iconColor: "text-blue-500" },
  { iconBg: "bg-purple-500/10", iconColor: "text-purple-500" },
  { iconBg: "bg-green-500/10", iconColor: "text-green-500" },
  { iconBg: "bg-red-500/10", iconColor: "text-red-500" },
];

type DisciplinaData = {
  id: number;
  slug: string;
  nome: string;
  descricao: string | null;
  icon: string;
  icon_color: string;
  total_aulas: number;
};

export default function DisciplinasPage() {
  const [disciplinas, setDisciplinas] = useState<DisciplinaData[]>([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [nome, setNome] = useState("");
  const [descricao, setDescricao] = useState("");
  const [creating, setCreating] = useState(false);

  const fetchDisciplinas = () => {
    apiFetch("/api/disciplinas")
      .then((r) => r.json())
      .then((data) => setDisciplinas(data))
      .catch(console.error)
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchDisciplinas(); }, []);

  const handleCreate = async () => {
    if (!nome.trim() || creating) return;
    setCreating(true);
    try {
      const res = await apiFetch("/api/disciplinas", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ nome: nome.trim(), descricao: descricao.trim() || null }),
      });
      if (!res.ok) {
        const err = await res.json();
        alert(err.detail || "Erro ao criar disciplina");
        return;
      }
      setNome("");
      setDescricao("");
      setShowForm(false);
      fetchDisciplinas();
    } catch (err) {
      console.error(err);
    } finally {
      setCreating(false);
    }
  };

  return (
    <>
      <header className="hidden md:flex sticky top-0 z-30 bg-bg-dark/80 backdrop-blur-md border-b border-border-dark px-8 py-4 justify-between items-center">
        <h1 className="text-2xl font-bold text-fg-strong flex items-center gap-2">
          <span className="material-symbols-outlined text-primary">library_books</span>
          Disciplinas
        </h1>
      </header>

      <main className="w-full px-4 md:px-8 py-8 overflow-y-auto h-full">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-center mb-8 gap-4">
          <div className="flex flex-col gap-1">
            <h2 className="text-3xl font-bold text-fg-strong">Minhas Disciplinas</h2>
            <p className="text-sm text-fg-muted">Organize suas aulas por matéria. Suba PDFs e deixe a IA trabalhar.</p>
          </div>
          <button
            onClick={() => setShowForm(!showForm)}
            className="flex items-center gap-2 px-5 py-2.5 bg-primary hover:bg-cyan-600 text-white rounded-lg shadow-lg shadow-cyan-500/20 transition-all font-medium whitespace-nowrap"
          >
            <span className="material-symbols-outlined text-sm">add</span>
            Nova Disciplina
          </button>
        </div>

        {/* Form de criação */}
        {showForm && (
          <div className="bg-surface-dark border border-border-dark rounded-xl p-6 mb-8 max-w-lg">
            <h3 className="text-sm font-semibold text-fg-strong mb-4 flex items-center gap-2">
              <span className="material-symbols-outlined text-primary text-[18px]">add_circle</span>
              Criar Disciplina
            </h3>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-fg-muted uppercase tracking-wider mb-1">Nome</label>
                <input
                  value={nome}
                  onChange={(e) => setNome(e.target.value)}
                  placeholder="Ex: Geotecnia, Cálculo III..."
                  className="w-full px-4 py-2.5 bg-bg-dark border border-border-dark rounded-lg text-sm text-fg-strong placeholder:text-fg-faint focus:ring-1 focus:ring-primary focus:border-primary"
                  onKeyDown={(e) => e.key === "Enter" && handleCreate()}
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-fg-muted uppercase tracking-wider mb-1">Descrição (opcional)</label>
                <input
                  value={descricao}
                  onChange={(e) => setDescricao(e.target.value)}
                  placeholder="Ex: Prof. Silva, 2025.1"
                  className="w-full px-4 py-2.5 bg-bg-dark border border-border-dark rounded-lg text-sm text-fg-strong placeholder:text-fg-faint focus:ring-1 focus:ring-primary focus:border-primary"
                />
              </div>
              <div className="flex gap-3">
                <button
                  onClick={handleCreate}
                  disabled={!nome.trim() || creating}
                  className="flex items-center gap-2 px-5 py-2.5 bg-primary hover:bg-cyan-600 text-white rounded-lg font-medium transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {creating ? "Criando..." : "Criar"}
                </button>
                <button
                  onClick={() => setShowForm(false)}
                  className="px-5 py-2.5 bg-surface-dark border border-border-strong text-fg rounded-lg font-medium hover:bg-surface-2 transition-colors"
                >
                  Cancelar
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Grid de disciplinas */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6 pb-8">
          {loading
            ? Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="bg-surface-dark rounded-xl border border-border-dark p-6 animate-pulse min-h-[200px]">
                  <div className="h-10 w-10 rounded-lg bg-surface-2 mb-4" />
                  <div className="h-5 w-32 bg-surface-2 rounded mb-2" />
                  <div className="h-3 w-24 bg-inset rounded" />
                </div>
              ))
            : disciplinas.map((disc, idx) => (
                <DisciplinaCard key={disc.id} disc={disc} colorIdx={idx} />
              ))}

          {!loading && disciplinas.length === 0 && !showForm && (
            <button
              onClick={() => setShowForm(true)}
              className="bg-surface-dark rounded-xl border border-dashed border-border hover:border-primary transition-all group flex flex-col h-full items-center justify-center cursor-pointer min-h-[200px]"
            >
              <div className="h-16 w-16 rounded-full bg-surface-2 flex items-center justify-center mb-4 group-hover:bg-primary/10 transition-colors">
                <span className="material-symbols-outlined text-3xl text-fg-muted group-hover:text-primary">add</span>
              </div>
              <h3 className="text-lg font-bold text-fg-strong mb-2">Primeira Disciplina</h3>
              <p className="text-sm text-fg-muted text-center px-6">
                Crie sua primeira disciplina para começar a organizar suas aulas.
              </p>
            </button>
          )}
        </div>
      </main>
    </>
  );
}

function DisciplinaCard({ disc, colorIdx }: { disc: DisciplinaData; colorIdx: number }) {
  const colors = DISC_COLORS[colorIdx % DISC_COLORS.length];

  return (
    <Link
      href={`/disciplinas/${disc.slug}`}
      className="bg-surface-dark rounded-xl border border-border-dark shadow-sm hover:shadow-md hover:border-primary/50 transition-all group flex flex-col"
    >
      <div className="p-6 flex-1">
        <div className="flex justify-between items-start mb-4">
          <div className={`h-12 w-12 rounded-lg ${colors.iconBg} flex items-center justify-center ${colors.iconColor}`}>
            <span className="material-symbols-outlined text-[28px]">{disc.icon}</span>
          </div>
          <span className="text-xs text-fg-faint bg-surface-2 px-2 py-1 rounded-full">
            {disc.total_aulas} {disc.total_aulas === 1 ? "aula" : "aulas"}
          </span>
        </div>
        <h3 className="text-lg font-bold text-fg-strong mb-1 group-hover:text-primary transition-colors">{disc.nome}</h3>
        {disc.descricao && (
          <p className="text-sm text-fg-muted line-clamp-2">{disc.descricao}</p>
        )}
      </div>

      <div className="px-6 pb-5 pt-2">
        <div className="flex items-center gap-2 text-xs text-primary font-medium group-hover:translate-x-1 transition-transform">
          <span>Ver aulas</span>
          <span className="material-symbols-outlined text-[16px]">arrow_forward</span>
        </div>
      </div>
    </Link>
  );
}

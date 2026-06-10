"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";

/**
 * /q/filtrar — Filtro facetado tipo TecConcursos.
 *
 * Layout adotado do TC (ver /docs/witdev-tec-master-ux.md §1):
 *   - Sidebar esquerda: 12 categorias fixas
 *   - Coluna central: árvore matéria→assunto OU lista de itens da categoria
 *   - Painel direito "Opções": chips dos filtros ativos
 *   - Bottom: contagem + "Gerar Caderno"
 */

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8011";

type Categoria = "Matéria e assunto" | "Banca" | "Órgão e cargo" | "Ano" | "Área (Carreira)"
  | "Escolaridade" | "Formação" | "Região" | "Favoritas" | "Enunciados" | "Opções";

const CATEGORIAS: Categoria[] = [
  "Matéria e assunto", "Banca", "Órgão e cargo", "Ano", "Área (Carreira)",
  "Escolaridade", "Formação", "Região", "Favoritas", "Enunciados", "Opções",
];

type TipoQuestao = "OBJETIVAS_TODAS" | "OBJETIVAS_INEDITAS" | "DISCURSIVAS";

interface MateriaArvore {
  id: number;
  nome: string;
  assuntos: { id: number; nome: string }[];
}

interface Filtros {
  materia?: string[];
  assuntos?: string[];
  banca?: string[];
  orgao?: string[];
  cargo?: string[];
  ano?: number[];
}

export default function FiltrarPage() {
  const router = useRouter();
  const [categoria, setCategoria] = useState<Categoria>("Matéria e assunto");
  const [tipoQ, setTipoQ] = useState<TipoQuestao>("OBJETIVAS_TODAS");
  const [filtros, setFiltros] = useState<Filtros>({});
  const [busca, setBusca] = useState("");
  const [arvore, setArvore] = useState<MateriaArvore[]>([]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [nomeCaderno, setNomeCaderno] = useState("Caderno de Estudo");
  const [gerando, setGerando] = useState(false);
  const [erroGerar, setErroGerar] = useState<string | null>(null);
  const [contagem, setContagem] = useState<{ total: number; facets: Record<string, Record<string, number>>; ms: number }>({
    total: 0,
    facets: {},
    ms: 0,
  });

  // Carrega árvore matéria→assunto
  useEffect(() => {
    fetch(`${API}/api/q/categorias-arvore`)
      .then((r) => r.json())
      .then(setArvore)
      .catch(console.error);
  }, []);

  // Carrega contagem + facetas sempre que filtros mudam (debounce 250ms — padrão TC)
  useEffect(() => {
    const t = setTimeout(() => {
      fetch(`${API}/api/q/count`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filtros }),
      })
        .then((r) => r.json())
        .then(setContagem)
        .catch(console.error);
    }, 250);
    return () => clearTimeout(t);
  }, [filtros]);

  const arvoreFiltrada = useMemo(() => {
    if (!busca) return arvore;
    const lower = busca.toLowerCase();
    return arvore
      .map((m) => ({
        ...m,
        assuntos: m.assuntos.filter((a) => a.nome.toLowerCase().includes(lower)),
        match: m.nome.toLowerCase().includes(lower),
      }))
      .filter((m) => m.match || m.assuntos.length > 0);
  }, [arvore, busca]);

  function togglePasta(id: number) {
    setExpanded((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id); else n.add(id);
      return n;
    });
  }

  function toggleAssunto(nome: string) {
    setFiltros((f) => {
      const cur = new Set(f.assuntos || []);
      if (cur.has(nome)) cur.delete(nome); else cur.add(nome);
      return { ...f, assuntos: Array.from(cur) };
    });
  }

  function selecionarMateriaInteira(m: MateriaArvore) {
    setFiltros((f) => {
      const cur = new Set(f.assuntos || []);
      m.assuntos.forEach((a) => cur.add(a.nome));
      return { ...f, assuntos: Array.from(cur) };
    });
  }

  async function gerarCaderno() {
    setErroGerar(null);
    setGerando(true);
    try {
      const r = await fetch(`${API}/api/q/cadernos`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          nome: nomeCaderno || "Caderno de Estudo",
          filtros,
          limite: Math.max(contagem.total, 1),
          ordem: "aleatoria",
        }),
      });
      const data = await r.json();
      if (!r.ok) {
        setErroGerar(data.detail || `HTTP ${r.status}`);
      } else {
        router.push(data.redirect || `/q/caderno/${data.id}`);
      }
    } catch (e: unknown) {
      setErroGerar((e as Error).message);
    } finally {
      setGerando(false);
    }
  }

  function removerChip(campo: keyof Filtros, valor: string | number) {
    setFiltros((f) => ({
      ...f,
      [campo]: (f[campo] as Array<string | number> | undefined)?.filter((v) => v !== valor),
    }));
  }

  const totalChips =
    (filtros.assuntos?.length || 0) + (filtros.banca?.length || 0) +
    (filtros.orgao?.length || 0) + (filtros.cargo?.length || 0) +
    (filtros.ano?.length || 0);

  return (
    <div className="min-h-screen bg-[#121212] text-gray-200">
      <header className="border-b border-gray-700 px-6 py-3 flex items-center justify-between">
        <h1 className="text-xl font-semibold">Filtrar Questões</h1>
        <div className="flex gap-4 text-sm">
          {(["OBJETIVAS_TODAS", "OBJETIVAS_INEDITAS", "DISCURSIVAS"] as TipoQuestao[]).map((t) => (
            <label key={t} className="flex items-center gap-2 cursor-pointer">
              <input type="radio" name="tipoQ" checked={tipoQ === t} onChange={() => setTipoQ(t)} />
              {t === "OBJETIVAS_TODAS" ? "Objetivas (todas)" :
                t === "OBJETIVAS_INEDITAS" ? "Objetivas (inéditas)" : "Discursivas"}
            </label>
          ))}
        </div>
      </header>

      <div className="grid grid-cols-[200px_1fr_280px] min-h-[calc(100vh-60px)]">
        {/* Sidebar categorias */}
        <aside className="border-r border-gray-700 py-2">
          {CATEGORIAS.map((c) => (
            <button
              key={c}
              onClick={() => setCategoria(c)}
              className={`block w-full text-left px-4 py-2 text-sm hover:bg-gray-800 ${
                categoria === c ? "bg-cyan-950 border-l-2 border-cyan-500 text-cyan-300" : ""
              }`}
            >
              {c}
            </button>
          ))}
        </aside>

        {/* Coluna central */}
        <section className="p-4 overflow-y-auto max-h-[calc(100vh-60px)]">
          <input
            type="text"
            placeholder="Pesquisar por nome…"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            className="w-full mb-3 px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm focus:outline-none focus:border-cyan-500"
          />

          {categoria === "Matéria e assunto" && (
            <ul className="space-y-0.5">
              {arvoreFiltrada.map((m) => (
                <li key={m.id}>
                  <button
                    onClick={() => togglePasta(m.id)}
                    className="w-full text-left flex items-center gap-2 px-2 py-1.5 hover:bg-gray-800 rounded text-sm"
                  >
                    <span className="text-yellow-500">📁</span>
                    <span className={expanded.has(m.id) ? "font-semibold" : ""}>{m.nome}</span>
                    <span className="ml-auto text-xs text-gray-500">{contagem.facets["materia"]?.[m.nome] || 0}</span>
                  </button>
                  {expanded.has(m.id) && (
                    <ul className="pl-8 space-y-0.5 mt-0.5">
                      <li>
                        <button
                          onClick={() => selecionarMateriaInteira(m)}
                          className="text-left px-2 py-1 text-xs text-cyan-400 hover:bg-gray-800 rounded w-full"
                        >
                          ✓ Todo o conteúdo de &quot;{m.nome}&quot;
                        </button>
                      </li>
                      {m.assuntos.map((a) => (
                        <li key={a.id}>
                          <button
                            onClick={() => toggleAssunto(a.nome)}
                            className={`text-left px-2 py-1 text-sm hover:bg-gray-800 rounded w-full flex items-center justify-between ${
                              filtros.assuntos?.includes(a.nome) ? "text-cyan-400 font-medium" : ""
                            }`}
                          >
                            <span>📄 {a.nome}</span>
                            <span className="text-xs text-gray-500">{contagem.facets["assuntos"]?.[a.nome] || 0}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}

          {categoria === "Banca" && (
            <ul className="space-y-1">
              {Object.entries(contagem.facets["banca"] || {})
                .filter(([nome]) => !busca || nome.toLowerCase().includes(busca.toLowerCase()))
                .sort((a, b) => b[1] - a[1])
                .map(([nome, n]) => (
                <li key={nome}>
                  <button
                    onClick={() => setFiltros((f) => ({ ...f, banca: f.banca?.includes(nome) ? f.banca.filter((b) => b !== nome) : [...(f.banca || []), nome] }))}
                    className={`text-left px-2 py-1 text-sm hover:bg-gray-800 rounded w-full flex justify-between ${
                      filtros.banca?.includes(nome) ? "text-cyan-400 font-medium" : ""
                    }`}
                  >
                    <span>{nome}</span>
                    <span className="text-xs text-gray-500">{n}</span>
                  </button>
                </li>
              ))}
            </ul>
          )}

          {categoria !== "Matéria e assunto" && categoria !== "Banca" && (
            <p className="text-sm text-gray-500 italic">Categoria &quot;{categoria}&quot;: dados virão dos facets quando a base crescer.</p>
          )}
        </section>

        {/* Painel direito Opções */}
        <aside className="border-l border-gray-700 p-4 bg-[#0a0a0a]">
          <h2 className="text-sm font-semibold mb-3 text-gray-400">
            Filtros ativos: <span className="text-cyan-400">{totalChips}</span>
          </h2>
          <div className="space-y-2 mb-4">
            {(filtros.assuntos || []).map((a) => (
              <div key={a} className="flex items-center justify-between bg-cyan-950 border border-cyan-800 rounded px-2 py-1 text-xs">
                <span className="truncate">{a}</span>
                <button onClick={() => removerChip("assuntos", a)} className="ml-2 text-red-400 hover:text-red-300">✕</button>
              </div>
            ))}
            {(filtros.banca || []).map((b) => (
              <div key={b} className="flex items-center justify-between bg-violet-950 border border-violet-800 rounded px-2 py-1 text-xs">
                <span className="truncate">Banca: {b}</span>
                <button onClick={() => removerChip("banca", b)} className="ml-2 text-red-400 hover:text-red-300">✕</button>
              </div>
            ))}
          </div>
          <div className="text-xs text-gray-500 mb-1">Atalhos:</div>
          <button className="text-xs text-cyan-400 hover:underline block">Remover anuladas</button>
          <button className="text-xs text-cyan-400 hover:underline block">Remover desatualizadas</button>
        </aside>
      </div>

      <footer className="border-t border-gray-700 px-6 py-4 bg-[#0a0a0a] flex items-center gap-4">
        <div className="flex-1">
          <div className="text-2xl font-semibold text-cyan-400">
            {contagem.total.toLocaleString("pt-BR")} <span className="text-base text-gray-400">questões encontradas</span>
          </div>
          <div className="text-xs text-gray-500">Meili: {contagem.ms}ms</div>
        </div>
        <div className="flex gap-2 items-center">
          <input
            type="text"
            value={nomeCaderno}
            onChange={(e) => setNomeCaderno(e.target.value)}
            placeholder="Nome do caderno"
            className="px-3 py-2 bg-gray-800 border border-gray-700 rounded text-sm"
            disabled={gerando}
          />
          <button
            onClick={gerarCaderno}
            disabled={gerando || contagem.total === 0}
            className="bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-700 disabled:cursor-not-allowed px-4 py-2 rounded text-sm font-semibold"
          >
            {gerando ? "Gerando…" : "GERAR CADERNO"}
          </button>
        </div>
      </footer>
      {erroGerar && (
        <div className="fixed bottom-20 right-6 bg-red-950 border border-red-700 rounded p-3 text-xs max-w-sm">
          Erro: {erroGerar}
        </div>
      )}
    </div>
  );
}

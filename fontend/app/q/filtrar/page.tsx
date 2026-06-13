"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";

/**
 * /q/filtrar — Filtro facetado tipo TecConcursos.
 *
 * Layout adotado do TC (ver /docs/witdev-tec-master-ux.md §1):
 *   - Sidebar esquerda: categorias fixas
 *   - Coluna central: árvore matéria→assunto OU lista de facetas da categoria
 *   - Painel direito "Opções": chips dos filtros ativos + atalhos
 *   - Bottom: contagem + nome/pasta + "Gerar Caderno"
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

type CampoFacet = "banca" | "orgao" | "cargo" | "ano" | "area" | "escolaridade" | "formacao" | "regiao";

interface Filtros {
  materia?: string[];
  assuntos?: string[];
  banca?: string[];
  orgao?: string[];
  cargo?: string[];
  ano?: number[];
  area?: string[];
  escolaridade?: string[];
  formacao?: string[];
  regiao?: string[];
  status_excluir?: string[];
}

// Categorias que são pura lista de facetas Meili (as demais têm UI própria)
const GRUPOS_FACET: Partial<Record<Categoria, { campo: CampoFacet; titulo?: string }[]>> = {
  "Banca": [{ campo: "banca" }],
  "Órgão e cargo": [
    { campo: "orgao", titulo: "Órgão" },
    { campo: "cargo", titulo: "Cargo" },
  ],
  "Ano": [{ campo: "ano" }],
  "Área (Carreira)": [{ campo: "area" }],
  "Escolaridade": [{ campo: "escolaridade" }],
  "Formação": [{ campo: "formacao" }],
  "Região": [{ campo: "regiao" }],
};

// Categorias cujos dados ainda não vêm na API de questões do TC
const NOTA_SEM_DADOS: Partial<Record<Categoria, string>> = {
  "Escolaridade": "A API de questões do TC não envia escolaridade por questão. O filtro ativa automaticamente quando a base tiver esse dado.",
  "Região": "A API de questões do TC não envia região/UF por questão. O filtro ativa automaticamente quando a base tiver esse dado.",
};

const CHIP_PREFIX: Record<string, string> = {
  assuntos: "",
  banca: "Banca: ",
  orgao: "Órgão: ",
  cargo: "Cargo: ",
  ano: "Ano: ",
  area: "Área: ",
  escolaridade: "Escolaridade: ",
  formacao: "Formação: ",
  regiao: "Região: ",
  status_excluir: "Sem ",
};

const CAMPOS_CHIP = Object.keys(CHIP_PREFIX) as (keyof Filtros & string)[];

export default function FiltrarPage() {
  const router = useRouter();
  const [categoria, setCategoria] = useState<Categoria>("Matéria e assunto");
  const [tipoQ, setTipoQ] = useState<TipoQuestao>("OBJETIVAS_TODAS");
  const [filtros, setFiltros] = useState<Filtros>({});
  const [favoritas, setFavoritas] = useState(false);
  const [favTotal, setFavTotal] = useState<number | null>(null);
  const [qEnunciado, setQEnunciado] = useState("");
  const [busca, setBusca] = useState("");
  const [arvore, setArvore] = useState<MateriaArvore[]>([]);
  const [expanded, setExpanded] = useState<Set<number>>(new Set());
  const [nomeCaderno, setNomeCaderno] = useState("Caderno de Estudo");
  const [pastaCaderno, setPastaCaderno] = useState("");
  const [pastas, setPastas] = useState<string[]>([]);
  const [gerando, setGerando] = useState(false);
  const [erroGerar, setErroGerar] = useState<string | null>(null);
  const [contagem, setContagem] = useState<{ total: number; facets: Record<string, Record<string, number>>; ms: number }>({
    total: 0,
    facets: {},
    ms: 0,
  });

  // Radio do topo → filtro `tipo` (inéditas ainda sem flag indexada — tratado como todas)
  const filtrosEnvio = useMemo<Record<string, Array<string | number>>>(() => ({
    ...filtros,
    tipo: tipoQ === "DISCURSIVAS" ? ["DISCURSIVA"] : ["MULTIPLA_ESCOLHA", "CERTO_ERRADO"],
  }), [filtros, tipoQ]);

  // Carrega árvore matéria→assunto, contagem de favoritas e pastas existentes
  useEffect(() => {
    fetch(`${API}/api/q/categorias-arvore`)
      .then((r) => r.json())
      .then(setArvore)
      .catch(console.error);
    fetch(`${API}/api/q/favoritas`)
      .then((r) => r.json())
      .then((d) => setFavTotal(d.total ?? 0))
      .catch(console.error);
    fetch(`${API}/api/q/pastas`)
      .then((r) => r.json())
      .then((rows: { pasta: string | null }[]) => setPastas(rows.map((p) => p.pasta).filter(Boolean) as string[]))
      .catch(console.error);
  }, []);

  // Carrega contagem + facetas sempre que filtros mudam (debounce 250ms — padrão TC)
  useEffect(() => {
    const t = setTimeout(() => {
      fetch(`${API}/api/q/count`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ filtros: filtrosEnvio, q: qEnunciado, favoritas }),
      })
        .then((r) => r.json())
        .then(setContagem)
        .catch(console.error);
    }, 250);
    return () => clearTimeout(t);
  }, [filtrosEnvio, qEnunciado, favoritas]);

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

  function toggleFacet(campo: CampoFacet, valor: string) {
    setFiltros((f) => {
      const atual = (f[campo] || []) as Array<string | number>;
      const marcado = atual.some((x) => String(x) === valor);
      const v: string | number = campo === "ano" ? Number(valor) : valor;
      return { ...f, [campo]: marcado ? atual.filter((x) => String(x) !== valor) : [...atual, v] };
    });
  }

  function toggleStatusExcluir(status: "ANULADA" | "DESATUALIZADA") {
    setFiltros((f) => {
      const cur = new Set(f.status_excluir || []);
      if (cur.has(status)) cur.delete(status); else cur.add(status);
      return { ...f, status_excluir: Array.from(cur) };
    });
  }

  /** Itens da faceta: distribuição Meili ∪ valores já selecionados (mesmo com count 0). */
  function itensFacet(campo: CampoFacet): [string, number][] {
    const dist = contagem.facets[campo] || {};
    const selecionados = ((filtros[campo] || []) as Array<string | number>).map(String);
    const chaves = new Set([...Object.keys(dist), ...selecionados]);
    let arr = Array.from(chaves).map((k) => [k, dist[k] || 0] as [string, number]);
    if (busca) arr = arr.filter(([k]) => k.toLowerCase().includes(busca.toLowerCase()));
    if (campo === "ano") arr.sort((a, b) => Number(b[0]) - Number(a[0]));
    else arr.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
    return arr;
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
          pasta: pastaCaderno.trim() || null,
          filtros: filtrosEnvio,
          q: qEnunciado,
          favoritas,
          limite: Math.min(Math.max(contagem.total, 1), 30000),
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

  function removerChip(campo: keyof Filtros, valor: string) {
    setFiltros((f) => ({
      ...f,
      [campo]: (f[campo] as Array<string | number> | undefined)?.filter((v) => String(v) !== valor),
    }));
  }

  const totalChips =
    CAMPOS_CHIP.reduce((n, campo) => n + ((filtros[campo] as unknown[] | undefined)?.length || 0), 0) +
    (favoritas ? 1 : 0) + (qEnunciado.trim() ? 1 : 0);

  const gruposDaCategoria = GRUPOS_FACET[categoria];

  return (
    <div className="min-h-screen bg-page text-fg">
      <header className="border-b border-border px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <h1 className="text-xl font-semibold">Filtrar Questões</h1>
          <Link href="/q/cadernos" className="text-sm text-primary hover:underline flex items-center gap-1">
            📁 Minhas pastas
          </Link>
        </div>
        <div className="flex gap-4 text-sm">
          {(["OBJETIVAS_TODAS", "OBJETIVAS_INEDITAS", "DISCURSIVAS"] as TipoQuestao[]).map((t) => (
            <label
              key={t}
              className={`flex items-center gap-2 ${t === "OBJETIVAS_INEDITAS" ? "opacity-50 cursor-not-allowed" : "cursor-pointer"}`}
              title={t === "OBJETIVAS_INEDITAS" ? "Flag de inédita ainda não indexada" : undefined}
            >
              <input
                type="radio"
                name="tipoQ"
                checked={tipoQ === t}
                onChange={() => setTipoQ(t)}
                disabled={t === "OBJETIVAS_INEDITAS"}
              />
              {t === "OBJETIVAS_TODAS" ? "Objetivas (todas)" :
                t === "OBJETIVAS_INEDITAS" ? "Objetivas (inéditas)" : "Discursivas"}
            </label>
          ))}
        </div>
      </header>

      <div className="grid grid-cols-[200px_1fr_280px] min-h-[calc(100vh-60px)]">
        {/* Sidebar categorias */}
        <aside className="border-r border-border py-2">
          {CATEGORIAS.map((c) => (
            <button
              key={c}
              onClick={() => setCategoria(c)}
              className={`block w-full text-left px-4 py-2 text-sm hover:bg-surface-2 ${
                categoria === c ? "bg-primary/10 border-l-2 border-primary text-primary" : ""
              }`}
            >
              {c}
            </button>
          ))}
        </aside>

        {/* Coluna central */}
        <section className="p-4 overflow-y-auto max-h-[calc(100vh-60px)]">
          {(categoria === "Matéria e assunto" || gruposDaCategoria) && (
            <input
              type="text"
              placeholder="Pesquisar por nome…"
              value={busca}
              onChange={(e) => setBusca(e.target.value)}
              className="w-full mb-3 px-3 py-2 bg-surface-2 border border-border rounded text-sm focus:outline-none focus:border-primary"
            />
          )}

          {categoria === "Matéria e assunto" && (
            <ul className="space-y-0.5">
              {arvoreFiltrada.map((m) => (
                <li key={m.id}>
                  <button
                    onClick={() => togglePasta(m.id)}
                    className="w-full text-left flex items-center gap-2 px-2 py-1.5 hover:bg-surface-2 rounded text-sm"
                  >
                    <span className="text-yellow-500">📁</span>
                    <span className={expanded.has(m.id) ? "font-semibold" : ""}>{m.nome}</span>
                    <span className="ml-auto text-xs text-fg-faint">{contagem.facets["materia"]?.[m.nome] || 0}</span>
                  </button>
                  {expanded.has(m.id) && (
                    <ul className="pl-8 space-y-0.5 mt-0.5">
                      <li>
                        <button
                          onClick={() => selecionarMateriaInteira(m)}
                          className="text-left px-2 py-1 text-xs text-primary hover:bg-surface-2 rounded w-full"
                        >
                          ✓ Todo o conteúdo de &quot;{m.nome}&quot;
                        </button>
                      </li>
                      {m.assuntos.map((a) => (
                        <li key={a.id}>
                          <button
                            onClick={() => toggleAssunto(a.nome)}
                            className={`text-left px-2 py-1 text-sm hover:bg-surface-2 rounded w-full flex items-center justify-between ${
                              filtros.assuntos?.includes(a.nome) ? "text-primary font-medium" : ""
                            }`}
                          >
                            <span>📄 {a.nome}</span>
                            <span className="text-xs text-fg-faint">{contagem.facets["assuntos"]?.[a.nome] || 0}</span>
                          </button>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              ))}
            </ul>
          )}

          {gruposDaCategoria && gruposDaCategoria.map(({ campo, titulo }) => {
            const itens = itensFacet(campo);
            return (
              <div key={campo} className="mb-4">
                {titulo && <h3 className="text-xs uppercase tracking-wide text-fg-faint mb-1 px-2">{titulo}</h3>}
                {itens.length === 0 ? (
                  <p className="text-sm text-fg-faint italic px-2">
                    {NOTA_SEM_DADOS[categoria] || "Nenhum item disponível com os filtros atuais."}
                  </p>
                ) : (
                  <ul className="space-y-1">
                    {itens.map(([nome, n]) => {
                      const ativo = ((filtros[campo] || []) as Array<string | number>).some((x) => String(x) === nome);
                      return (
                        <li key={nome}>
                          <button
                            onClick={() => toggleFacet(campo, nome)}
                            className={`text-left px-2 py-1 text-sm hover:bg-surface-2 rounded w-full flex justify-between ${
                              ativo ? "text-primary font-medium" : ""
                            }`}
                          >
                            <span className="truncate">{ativo ? "✓ " : ""}{nome}</span>
                            <span className="text-xs text-fg-faint shrink-0 ml-2">{n}</span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </div>
            );
          })}

          {categoria === "Favoritas" && (
            <div className="space-y-3">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input type="checkbox" checked={favoritas} onChange={(e) => setFavoritas(e.target.checked)} />
                Apenas questões favoritas
              </label>
              <p className="text-xs text-fg-faint">
                {favTotal === null ? "Carregando…" : `${favTotal} questão(ões) favoritada(s).`}{" "}
                Marque a estrela ⭐ no cabeçalho da questão dentro de um caderno para favoritar.
              </p>
            </div>
          )}

          {categoria === "Enunciados" && (
            <div className="space-y-2">
              <input
                type="text"
                placeholder="Palavras no enunciado…"
                value={qEnunciado}
                onChange={(e) => setQEnunciado(e.target.value)}
                className="w-full px-3 py-2 bg-surface-2 border border-border rounded text-sm focus:outline-none focus:border-primary"
              />
              <p className="text-xs text-fg-faint">
                Busca textual no enunciado das questões (Meilisearch). Combine com os demais filtros.
              </p>
            </div>
          )}

          {categoria === "Opções" && (
            <div className="space-y-3">
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={(filtros.status_excluir || []).includes("ANULADA")}
                  onChange={() => toggleStatusExcluir("ANULADA")}
                />
                Remover questões anuladas
              </label>
              <label className="flex items-center gap-2 text-sm cursor-pointer">
                <input
                  type="checkbox"
                  checked={(filtros.status_excluir || []).includes("DESATUALIZADA")}
                  onChange={() => toggleStatusExcluir("DESATUALIZADA")}
                />
                Remover questões desatualizadas
              </label>
            </div>
          )}
        </section>

        {/* Painel direito Opções */}
        <aside className="border-l border-border p-4 bg-page">
          <h2 className="text-sm font-semibold mb-3 text-fg-muted">
            Filtros ativos: <span className="text-primary">{totalChips}</span>
          </h2>
          <div className="space-y-2 mb-4 max-h-[50vh] overflow-y-auto">
            {favoritas && (
              <div className="flex items-center justify-between bg-warning/15 border border-warning/40 rounded px-2 py-1 text-xs">
                <span className="truncate">⭐ Apenas favoritas</span>
                <button onClick={() => setFavoritas(false)} className="ml-2 text-error hover:text-error">✕</button>
              </div>
            )}
            {qEnunciado.trim() && (
              <div className="flex items-center justify-between bg-surface-2 border border-border rounded px-2 py-1 text-xs">
                <span className="truncate">Enunciado: “{qEnunciado.trim()}”</span>
                <button onClick={() => setQEnunciado("")} className="ml-2 text-error hover:text-error">✕</button>
              </div>
            )}
            {CAMPOS_CHIP.flatMap((campo) =>
              ((filtros[campo] || []) as Array<string | number>).map((v) => (
                <div
                  key={`${campo}:${v}`}
                  className={`flex items-center justify-between rounded px-2 py-1 text-xs border ${
                    campo === "assuntos"
                      ? "bg-primary/10 border-primary/40"
                      : campo === "status_excluir"
                        ? "bg-error/10 border-error/40"
                        : "bg-secondary/10 border-secondary/40"
                  }`}
                >
                  <span className="truncate">
                    {campo === "status_excluir" ? `Sem ${String(v).toLowerCase()}s` : `${CHIP_PREFIX[campo]}${v}`}
                  </span>
                  <button onClick={() => removerChip(campo, String(v))} className="ml-2 text-error hover:text-error">✕</button>
                </div>
              ))
            )}
          </div>
          <div className="text-xs text-fg-faint mb-1">Atalhos:</div>
          <button
            onClick={() => toggleStatusExcluir("ANULADA")}
            className="text-xs text-primary hover:underline block"
          >
            {(filtros.status_excluir || []).includes("ANULADA") ? "✓ Anuladas removidas" : "Remover anuladas"}
          </button>
          <button
            onClick={() => toggleStatusExcluir("DESATUALIZADA")}
            className="text-xs text-primary hover:underline block"
          >
            {(filtros.status_excluir || []).includes("DESATUALIZADA") ? "✓ Desatualizadas removidas" : "Remover desatualizadas"}
          </button>
        </aside>
      </div>

      <footer className="border-t border-border px-6 py-4 bg-page flex items-center gap-4">
        <div className="flex-1">
          <div className="text-2xl font-semibold text-primary">
            {contagem.total.toLocaleString("pt-BR")} <span className="text-base text-fg-muted">questões encontradas</span>
          </div>
          <div className="text-xs text-fg-faint">Meili: {contagem.ms}ms</div>
        </div>
        <div className="flex gap-2 items-center">
          <input
            type="text"
            value={pastaCaderno}
            onChange={(e) => setPastaCaderno(e.target.value)}
            placeholder="Pasta (opcional)"
            list="pastas-existentes"
            className="px-3 py-2 bg-surface-2 border border-border rounded text-sm w-44"
            disabled={gerando}
          />
          <datalist id="pastas-existentes">
            {pastas.map((p) => <option key={p} value={p} />)}
          </datalist>
          <input
            type="text"
            value={nomeCaderno}
            onChange={(e) => setNomeCaderno(e.target.value)}
            placeholder="Nome do caderno"
            className="px-3 py-2 bg-surface-2 border border-border rounded text-sm"
            disabled={gerando}
          />
          <button
            onClick={gerarCaderno}
            disabled={gerando || contagem.total === 0}
            className="bg-cyan-600 hover:bg-cyan-500 disabled:bg-surface-2 disabled:cursor-not-allowed px-4 py-2 rounded text-sm font-semibold"
          >
            {gerando ? "Gerando…" : "GERAR CADERNO"}
          </button>
        </div>
      </footer>
      {erroGerar && (
        <div className="fixed bottom-20 right-6 bg-error/10 border border-error/40 rounded p-3 text-xs max-w-sm">
          Erro: {erroGerar}
        </div>
      )}
    </div>
  );
}

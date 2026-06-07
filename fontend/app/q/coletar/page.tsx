"use client";

import { useState } from "react";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8011";

interface Resultado {
  caderno_id: number;
  scraper: { ok: number; erro: number; paginas: number };
  pre_total: number;
  pos_total: number;
  novas: number;
  atualizadas: number;
  meili_reindexadas: number;
}

export default function ColetarPage() {
  const [url, setUrl] = useState("");
  const [relogin, setRelogin] = useState(false);
  const [carregando, setCarregando] = useState(false);
  const [resultado, setResultado] = useState<Resultado | null>(null);
  const [erro, setErro] = useState<string | null>(null);

  function extrairId(s: string): string | null {
    const t = s.trim();
    if (/^\d+$/.test(t)) return t;
    const m = t.match(/cadernos\/(\d+)/);
    return m ? m[1] : null;
  }

  const id = extrairId(url);

  async function coletar() {
    if (!id) {
      setErro("URL inválida. Cole algo como https://www.tecconcursos.com.br/questoes/cadernos/12345");
      return;
    }
    setErro(null);
    setResultado(null);
    setCarregando(true);
    try {
      const r = await fetch(`${API}/api/q/coletar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url, relogin }),
      });
      const data = await r.json();
      if (!r.ok) {
        setErro(data.detail || data.message || `HTTP ${r.status}`);
      } else {
        setResultado(data);
      }
    } catch (e: unknown) {
      setErro((e as Error).message);
    } finally {
      setCarregando(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#121212] text-gray-200">
      <header className="border-b border-gray-700 px-6 py-4">
        <h1 className="text-xl font-semibold flex items-center gap-2">
          <span>📥</span> Coletar caderno do TecConcursos
        </h1>
        <p className="text-xs text-gray-500 mt-1">
          Cole o link de um caderno do TC. O sistema usa o endpoint OURO
          (5 reqs ≈ 30s para 1000 questões), faz dedup por <code>id_externo</code>
          e reindexa Meilisearch automaticamente.
        </p>
      </header>

      <main className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <div>
          <label className="block text-sm font-semibold mb-2">
            URL ou ID do caderno
          </label>
          <input
            type="text"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://www.tecconcursos.com.br/questoes/cadernos/95846378"
            className="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-sm focus:outline-none focus:border-cyan-500 font-mono"
            disabled={carregando}
          />
          {id && (
            <div className="mt-2 text-xs text-cyan-400">
              ✓ Caderno detectado: <span className="font-mono font-semibold">#{id}</span>
            </div>
          )}
        </div>

        <label className="flex items-center gap-2 text-sm cursor-pointer">
          <input
            type="checkbox"
            checked={relogin}
            onChange={(e) => setRelogin(e.target.checked)}
            disabled={carregando}
          />
          Refazer login Playwright antes
          <span className="text-xs text-gray-500">
            (use se trocou IP ou faz tempo)
          </span>
        </label>

        <button
          onClick={coletar}
          disabled={!id || carregando}
          className="w-full bg-cyan-600 hover:bg-cyan-500 disabled:bg-gray-700 disabled:cursor-not-allowed px-6 py-3 rounded-lg font-semibold text-base"
        >
          {carregando ? "Coletando…" : "🚀 Iniciar coleta"}
        </button>

        {erro && (
          <div className="bg-red-950 border border-red-700 rounded p-4 text-sm">
            <strong className="text-red-400">Erro:</strong> {erro}
          </div>
        )}

        {resultado && (
          <div className="bg-green-950 border border-green-700 rounded-lg p-6 space-y-4">
            <h2 className="text-lg font-semibold text-green-300">
              ✅ Coleta concluída — caderno #{resultado.caderno_id}
            </h2>

            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-center">
              <div className="bg-black/30 rounded p-3">
                <div className="text-2xl font-bold text-cyan-400">
                  {resultado.scraper.ok}
                </div>
                <div className="text-xs text-gray-400">Coletadas</div>
              </div>
              <div className="bg-black/30 rounded p-3">
                <div className="text-2xl font-bold text-green-400">
                  {resultado.novas}
                </div>
                <div className="text-xs text-gray-400">Novas no banco</div>
              </div>
              <div className="bg-black/30 rounded p-3">
                <div className="text-2xl font-bold text-yellow-400">
                  {resultado.atualizadas}
                </div>
                <div className="text-xs text-gray-400">Dedup (já existiam)</div>
              </div>
              <div className="bg-black/30 rounded p-3">
                <div className="text-2xl font-bold text-violet-400">
                  {resultado.scraper.paginas}
                </div>
                <div className="text-xs text-gray-400">Reqs ao TC</div>
              </div>
            </div>

            <div className="text-xs text-gray-400 border-t border-green-800 pt-3 space-y-1">
              <div>
                <strong>Total no banco:</strong> {resultado.pre_total} →{" "}
                <span className="text-cyan-400 font-semibold">
                  {resultado.pos_total}
                </span>
              </div>
              <div>
                <strong>Meilisearch:</strong> {resultado.meili_reindexadas}{" "}
                documentos reindexados
              </div>
              <div>
                <strong>Erros do scraper:</strong> {resultado.scraper.erro}
              </div>
            </div>

            <div className="flex gap-2 pt-2">
              <a
                href="/q/filtrar"
                className="text-xs bg-cyan-700 hover:bg-cyan-600 px-3 py-2 rounded"
              >
                Ver no filtro →
              </a>
              <button
                onClick={() => {
                  setResultado(null);
                  setUrl("");
                }}
                className="text-xs bg-gray-700 hover:bg-gray-600 px-3 py-2 rounded"
              >
                Coletar outro caderno
              </button>
            </div>
          </div>
        )}

        <div className="text-xs text-gray-500 border-t border-gray-800 pt-4">
          <strong className="text-gray-400">Como a dedup funciona:</strong>
          <ul className="list-disc list-inside mt-1 space-y-0.5">
            <li>Cada questão tem <code>id_externo</code> UNIQUE no Postgres</li>
            <li>Coleta usa UPSERT — re-rodar o mesmo caderno apenas atualiza</li>
            <li>O <code>ScrapeState</code> SQLite marca por <code>idQuestao</code></li>
            <li>Múltiplos cadernos compartilham questões? OK — armazenadas 1x</li>
          </ul>
        </div>
      </main>
    </div>
  );
}

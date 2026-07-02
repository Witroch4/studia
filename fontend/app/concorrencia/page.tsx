"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import ConcursoUploader from "../components/ConcursoUploader";
import ConcursoGuiaCsv from "../components/ConcursoGuiaCsv";
import { apiFetch, apiJson } from "@/lib/api";
import { qk } from "@/lib/queryKeys";
import { authClient } from "@/lib/auth-client";

// ─── Identidade por modalidade ───────────────────────────
type Mod = "AC" | "PN" | "PI" | "PQ" | "PCD";
const MOD: Record<Mod, { nome: string; curto: string; text: string; bg: string; ring: string; bar: string; icon: string }> = {
  AC:  { nome: "Ampla Concorrência", curto: "Ampla", text: "text-primary",   bg: "bg-primary/10",   ring: "ring-primary/30",   bar: "bg-cyan-500",   icon: "groups" },
  PN:  { nome: "Pretos e Pardos",    curto: "Negros", text: "text-warning",  bg: "bg-warning/10",  ring: "ring-warning/30",  bar: "bg-amber-500",  icon: "diversity_3" },
  PI:  { nome: "Indígenas",          curto: "Indíg.", text: "text-success",bg: "bg-success/10",ring: "ring-success/30",bar: "bg-emerald-500",icon: "forest" },
  PQ:  { nome: "Quilombolas",        curto: "Quilom.",text: "text-secondary", bg: "bg-secondary/10", ring: "ring-secondary/30", bar: "bg-violet-500", icon: "cabin" },
  PCD: { nome: "Pessoa c/ Deficiência", curto: "PcD",  text: "text-primary",   bg: "bg-primary/10",    ring: "ring-primary/30",    bar: "bg-sky-500",    icon: "accessible" },
};
const ORDER: Mod[] = ["AC", "PN", "PI", "PQ", "PCD"];

type ConcursoMeta = {
  id: number; nome: string; total_candidatos: number;
  publico: boolean; meu: boolean;
  cargos: string[]; macropolos: string[];
  polos: { uf: string; total: number }[];
  cotas: Record<string, number>;
};
type SimResult = {
  distribuicao: { total: number; aplica_racial: boolean; vagas: Record<Mod, number>; convocados: Record<Mod, number>; fator_cr: number; reservadas: number; pct_reservado: number };
  criterio: "PONTOS" | "ESPECIFICO";
  max_esp: number;
  nota_corte: Record<string, number | null>;
  nota_corte_pct: Record<string, number | null>;
  grupos: Record<string, { sigla: Mod; nome: string; total_inscritos: number; deslocados_ampla: number; concorrem_reserva: number; vagas: number; convocados: number; preenchidas: number; nota_corte: number | null; nota_corte_pct: number | null; ultimo_aprovado: { polo: string; pontos: number } | null }>;
  total_candidatos: number;
  recorte: { cargo: string | null; abrangencia: string; valor: string | null; total_no_recorte: number };
  pessoal: null | { pontuacao: number; pontuacao_pct: number | null; criterio: string; max_esp: number; posicao_ac: number; convocados_ac: number; passa_ac: boolean; nota_corte_ac: number | null; falta_ac: number; categorias_info: { sigla: Mod; nome: string; posicao: number; convocados: number; passa: boolean; nota_corte: number | null; falta: number }[] };
  classificacao: ClassRow[];
  classificacao_total: number;
};
type ClassRow = {
  inscricao: string; polo: string; pontos: number; discursiva: number;
  tot_esp: number; l_port: number; l_ing: number;
  nota: number; nota_pct: number | null;
  rank_geral: number; entrou_por: Mod | null;
  is_negro: boolean; is_pcd: boolean; is_indigena: boolean; is_quilombola: boolean;
};

type ConcursoItem = {
  id: number; nome: string; total_candidatos: number; created_at: string | null;
  publico: boolean; meu: boolean; pode_excluir: boolean;
};

export default function ConcorrenciaPage() {
  const queryClient = useQueryClient();

  const [meta, setMeta] = useState<ConcursoMeta | null>(null);

  // Config da simulação
  const [cargo, setCargo] = useState<string>("");
  const [abrangencia, setAbrangencia] = useState<"GERAL" | "MACROPOLO" | "POLO">("GERAL");
  const [recorte, setRecorte] = useState<string>("");
  const [totalVagas, setTotalVagas] = useState(20);
  const [fatorCR, setFatorCR] = useState(3);
  const [pct, setPct] = useState({ pn: 25, pi: 3, pq: 2, pcd: 5 });
  const [criterio, setCriterio] = useState<"PONTOS" | "ESPECIFICO">("PONTOS");
  const [maxEsp, setMaxEsp] = useState(40);
  const [arredRacial, setArredRacial] = useState("MEIO");
  const [minhaPont, setMinhaPont] = useState<string>("");
  const [minhasCats, setMinhasCats] = useState<("PN" | "PI" | "PQ" | "PCD")[]>([]);
  const toggleCat = (c: "PN" | "PI" | "PQ" | "PCD") =>
    setMinhasCats((cur) => (cur.includes(c) ? cur.filter((x) => x !== c) : [...cur, c]));

  const [result, setResult] = useState<SimResult | null>(null);
  const [showLei, setShowLei] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Admin publica imports no catálogo. Mesmo padrão do Sidebar: better-auth é
  // externalizado, então a sessão só é lida no cliente (useEffect).
  const [isAdmin, setIsAdmin] = useState(false);
  useEffect(() => {
    authClient
      .getSession()
      .then((res) => {
        const role = (res?.data?.user as { role?: string } | undefined)?.role;
        setIsAdmin(role === "admin");
      })
      .catch(() => {});
  }, []);

  // ─── GET /api/concursos ──────────────────────────────────
  const { data: concursos = [], isPending: loadingList } = useQuery({
    queryKey: qk.concursos(),
    queryFn: () => apiJson<ConcursoItem[]>("/api/concursos"),
  });

  // ─── DELETE /api/concursos/{id} ──────────────────────────
  const deleteMutation = useMutation({
    mutationFn: (id: number) =>
      apiFetch(`/api/concursos/${id}`, { method: "DELETE" }).then((r) => {
        if (!r.ok) throw new Error("Erro ao excluir");
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.concursos() });
    },
  });

  // ─── POST /api/concursos/import ──────────────────────────
  const importMutation = useMutation({
    mutationFn: async ({ file, nome, publico }: { file: File; nome: string; publico: boolean }) => {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("nome", nome);
      fd.append("publico", publico ? "true" : "false");
      const res = await apiFetch("/api/concursos/import", { method: "POST", body: fd });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || "Erro ao importar");
      }
      return res.json() as Promise<{ id: number }>;
    },
    onSuccess: (data) => {
      queryClient.invalidateQueries({ queryKey: qk.concursos() });
      openConcurso(data.id);
    },
    onError: (err: Error) => {
      alert(err.message);
    },
  });

  // ─── POST /api/concursos/{id}/simular ───────────────────
  // Returns a simulation result shown in UI; does NOT change the concursos list.
  // useMutation gives us isPending for the spinner + result via onSuccess.
  const simularMutation = useMutation({
    mutationFn: async ({ id, body }: { id: number; body: object }) => {
      const r = await apiFetch(`/api/concursos/${id}/simular`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) throw new Error((await r.json()).detail);
      return r.json() as Promise<SimResult>;
    },
    onSuccess: (data) => {
      setResult(data);
    },
    onError: (err) => {
      console.error(err);
    },
  });

  // ─── On-demand GET /api/concursos/{id} (detail/meta) ───
  // Kept as apiFetch: it's a one-shot fetch triggered by user interaction
  // (selecting a concurso from the list or after import). Not a background
  // subscription, so useQuery with enabled would add complexity without benefit.
  const openConcurso = useCallback((id: number) => {
    apiFetch(`/api/concursos/${id}`)
      .then((r) => r.json())
      .then((m: ConcursoMeta) => {
        setMeta(m);
        setCargo(m.cargos[0] || "");
        setAbrangencia("GERAL");
        setRecorte("");
      })
      .catch(console.error);
  }, []);

  const handleUpload = async (file: File, nome: string, publico: boolean) => {
    importMutation.mutate({ file, nome, publico });
  };

  const runSim = useCallback(() => {
    if (!meta) return;
    const body = {
      cargo: cargo || null,
      abrangencia,
      recorte: abrangencia === "GERAL" ? null : recorte || null,
      total_vagas: totalVagas,
      fator_cr: fatorCR,
      pct_pn: pct.pn / 100, pct_pi: pct.pi / 100, pct_pq: pct.pq / 100, pct_pcd: pct.pcd / 100,
      arred_racial: arredRacial,
      criterio,
      max_esp: maxEsp,
      minha_pontuacao: minhaPont ? parseFloat(minhaPont) : null,
      minhas_categorias: minhasCats,
    };
    simularMutation.mutate({ id: meta.id, body });
  }, [meta, cargo, abrangencia, recorte, totalVagas, fatorCR, pct, arredRacial, criterio, maxEsp, minhaPont, minhasCats, simularMutation]);

  useEffect(() => {
    if (!meta) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(runSim, 320);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [meta, runSim]);

  const recorteOpts = useMemo(() => {
    if (!meta) return [];
    if (abrangencia === "MACROPOLO") return meta.macropolos;
    if (abrangencia === "POLO") return meta.polos.map((p) => p.uf);
    return [];
  }, [meta, abrangencia]);

  // Reset recorte when abrangencia changes — done in the event handler to avoid
  // calling setState inside a useEffect body (react-hooks/set-state-in-effect).
  const handleAbrangencia = useCallback(
    (next: "GERAL" | "MACROPOLO" | "POLO") => {
      setAbrangencia(next);
      if (next === "GERAL") {
        setRecorte("");
      } else {
        const opts =
          next === "MACROPOLO"
            ? (meta?.macropolos ?? [])
            : (meta?.polos.map((p) => p.uf) ?? []);
        if (opts.length) setRecorte(opts[0]);
      }
    },
    [meta],
  );

  const simLoading = simularMutation.isPending;

  // ─── Tela inicial: upload + lista ──────────────────────
  if (!meta) {
    return (
      <>
        <PageHeader />
        <main className="w-full px-4 md:px-8 py-8 overflow-y-auto h-full cc-grid">
          <div className="max-w-3xl mx-auto cc-reveal">
            <div className="mb-8">
              <p className="text-[11px] uppercase tracking-[0.25em] text-primary/80 font-semibold mb-2">Estudo de concorrência</p>
              <h2 className="text-4xl font-bold text-fg-strong leading-tight">Transforme o resultado<br />num <span className="text-primary">banco comparativo</span>.</h2>
              <p className="text-sm text-fg-muted mt-3 max-w-xl">
                Suba o CSV do concurso e simule notas de corte por estado e nacional — ampla, pretos/pardos, indígenas, quilombolas e PcD, com a regra de deslocamento da nova Lei de Cotas (Lei 15.142/2025).
              </p>
            </div>

            <div className="bg-surface-dark border border-border-dark rounded-2xl p-6 mb-4">
              <ConcursoUploader onUpload={handleUpload} uploading={importMutation.isPending} isAdmin={isAdmin} />
            </div>

            <div className="mb-8">
              <ConcursoGuiaCsv />
            </div>

            {loadingList ? (
              <>
                <div className="flex items-center gap-3 mb-4">
                  <span className="material-symbols-outlined text-fg-faint text-[20px]">public</span>
                  <h3 className="text-sm font-semibold text-fg uppercase tracking-wider">Catálogo de concorrências</h3>
                </div>
                <div className="space-y-2">
                  {Array.from({ length: 2 }).map((_, i) => <div key={i} className="h-16 bg-surface-dark border border-border-dark rounded-xl animate-pulse" />)}
                </div>
              </>
            ) : (
              <>
                <ListaConcursos
                  icon="public"
                  titulo="Catálogo de concorrências"
                  vazio="O catálogo ainda está vazio."
                  itens={concursos.filter((c) => c.publico)}
                  onOpen={openConcurso}
                  onDelete={(c) => deleteMutation.mutate(c.id)}
                  deletingId={deleteMutation.isPending ? (deleteMutation.variables ?? null) : null}
                />
                {concursos.some((c) => c.meu && !c.publico) && (
                  <div className="mt-8">
                    <ListaConcursos
                      icon="lock"
                      titulo="Meus concursos (só você vê)"
                      vazio=""
                      itens={concursos.filter((c) => c.meu && !c.publico)}
                      onOpen={openConcurso}
                      onDelete={(c) => deleteMutation.mutate(c.id)}
                      deletingId={deleteMutation.isPending ? (deleteMutation.variables ?? null) : null}
                    />
                  </div>
                )}
              </>
            )}
          </div>
        </main>
      </>
    );
  }

  // ─── Tela de estudo ────────────────────────────────────
  const d = result?.distribuicao;
  const pctPadrao = pct.pn === 25 && pct.pi === 3 && pct.pq === 2 && pct.pcd === 5;
  const presetAtivo: "CAIXA" | "CNU" | "" =
    pctPadrao && arredRacial === "MEIO"
      ? fatorCR === 4 && maxEsp === 40
        ? "CAIXA"
        : fatorCR === 3 && criterio === "PONTOS"
          ? "CNU"
          : ""
      : "";
  return (
    <>
      <PageHeader>
        <div className="flex items-center gap-3 min-w-0">
          <button onClick={() => { setMeta(null); setResult(null); }} className="text-fg-faint hover:text-fg-strong transition-colors shrink-0 cursor-pointer">
            <span className="material-symbols-outlined">arrow_back</span>
          </button>
          <div className="min-w-0">
            <p className="text-sm font-bold text-fg-strong truncate flex items-center gap-2">
              {meta.nome}
              {meta.publico && (
                <span className="inline-flex items-center gap-1 text-[9px] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded-full bg-primary/10 text-primary shrink-0">
                  <span className="material-symbols-outlined text-[11px]">public</span>catálogo
                </span>
              )}
            </p>
            <p className="text-[11px] text-fg-faint cc-num">{meta.total_candidatos.toLocaleString("pt-BR")} candidatos · {meta.cargos.length} cargo(s)</p>
          </div>
        </div>
      </PageHeader>

      <main className="w-full overflow-y-auto h-full cc-grid">
        <div className="flex flex-col xl:flex-row">
          {/* Painel de controle */}
          <aside className="xl:w-[340px] xl:shrink-0 xl:sticky xl:top-0 xl:h-[calc(100vh-1px)] xl:overflow-y-auto border-b xl:border-b-0 xl:border-r border-border-dark bg-surface-dark/60 backdrop-blur p-5 space-y-6">
            <Section icon="bookmark_star" title="Presets de concurso">
              <div className="grid grid-cols-1 gap-1.5">
                <button
                  onClick={() => { setPct({ pn: 25, pi: 3, pq: 2, pcd: 5 }); setArredRacial("MEIO"); setFatorCR(4); setMaxEsp(40); }}
                  className={`relative text-left px-3 py-2.5 rounded-lg border transition-all ${
                    presetAtivo === "CAIXA"
                      ? "border-warning bg-warning/15 ring-1 ring-warning/40"
                      : "border-border-dark bg-bg-dark hover:border-warning/40"
                  }`}
                >
                  {presetAtivo === "CAIXA" && (
                    <span className="material-symbols-outlined absolute top-2 right-2 text-warning text-[16px]">check_circle</span>
                  )}
                  <p className={`text-xs font-bold flex items-center gap-1.5 ${presetAtivo === "CAIXA" ? "text-warning" : "text-fg"}`}><span className="material-symbols-outlined text-[15px]">account_balance</span>Caixa 2025</p>
                  <p className="text-[10px] text-fg-faint mt-0.5">Fator 4 (imediatas + 3× CR) · cotas 25/3/2/5 · específica máx. 40</p>
                </button>
                <button
                  onClick={() => { setPct({ pn: 25, pi: 3, pq: 2, pcd: 5 }); setArredRacial("MEIO"); setFatorCR(3); setCriterio("PONTOS"); }}
                  className={`relative text-left px-3 py-2.5 rounded-lg border transition-all ${
                    presetAtivo === "CNU"
                      ? "border-primary bg-primary/15 ring-1 ring-primary/40"
                      : "border-border-dark bg-bg-dark hover:border-primary/40"
                  }`}
                >
                  {presetAtivo === "CNU" && (
                    <span className="material-symbols-outlined absolute top-2 right-2 text-primary text-[16px]">check_circle</span>
                  )}
                  <p className={`text-xs font-bold flex items-center gap-1.5 ${presetAtivo === "CNU" ? "text-white" : "text-fg"}`}><span className="material-symbols-outlined text-[15px]">balance</span>Padrão CNU (Lei 15.142/25)</p>
                  <p className="text-[10px] text-fg-faint mt-0.5">Fator 3 · cotas 25/3/2/5 · pontos totais</p>
                </button>
              </div>
              <p className="text-[10px] text-fg-faint leading-relaxed">
                Caixa: informe as <strong className="text-fg-muted">vagas imediatas</strong>; o fator 4 inclui as 3× do cadastro de reserva. O critério (pontos × específica) escolha abaixo conforme o cargo.
              </p>
            </Section>

            <Section icon="tune" title="Recorte da análise">
              {meta.cargos.length > 1 && (
                <Field label="Cargo">
                  <Select value={cargo} onChange={setCargo} options={meta.cargos} />
                </Field>
              )}
              <Field label="Abrangência">
                <div className="grid grid-cols-3 gap-1 p-1 bg-bg-dark rounded-lg border border-border-dark">
                  {(["GERAL", "MACROPOLO", "POLO"] as const).map((a) => (
                    <button key={a} onClick={() => handleAbrangencia(a)}
                      className={`text-[11px] font-semibold py-1.5 rounded-md transition-all ${abrangencia === a ? "bg-primary text-white shadow" : "text-fg-muted hover:text-fg-strong"}`}>
                      {a === "GERAL" ? "Nacional" : a === "MACROPOLO" ? "Região" : "Estado"}
                    </button>
                  ))}
                </div>
              </Field>
              {abrangencia !== "GERAL" && (
                <Field label={abrangencia === "MACROPOLO" ? "Região" : "Estado (polo)"}>
                  <Select value={recorte} onChange={setRecorte} options={recorteOpts} />
                </Field>
              )}
            </Section>

            <Section icon="confirmation_number" title="Vagas & cadastro de reserva">
              <Field label={`Total de vagas${abrangencia === "GERAL" ? " (nacional)" : ` (${recorte})`}`}>
                <Stepper value={totalVagas} onChange={setTotalVagas} min={1} max={9999} />
              </Field>
              <Field label={`Fator do cadastro de reserva — convocados = vagas × ${fatorCR}`}>
                <div className="flex items-center gap-3">
                  <input type="range" min={1} max={20} step={1} value={fatorCR} onChange={(e) => setFatorCR(+e.target.value)}
                    className="flex-1 accent-primary" />
                  <span className="cc-num text-sm font-bold text-primary w-8 text-right">{fatorCR}×</span>
                </div>
              </Field>
            </Section>

            <Section icon="rule" title="Critério de classificação">
              <div className="grid grid-cols-1 gap-1.5">
                <button onClick={() => setCriterio("PONTOS")}
                  className={`text-left px-3 py-2.5 rounded-lg border transition-all ${criterio === "PONTOS" ? "bg-primary/15 border-primary text-fg-strong" : "bg-bg-dark border-border-dark text-fg-muted hover:border-primary/40"}`}>
                  <p className="text-xs font-bold flex items-center gap-1.5"><span className="material-symbols-outlined text-[15px]">functions</span>Pontos totais (padrão CNU)</p>
                  <p className="text-[10px] text-fg-faint mt-0.5">Soma geral · desempate: discursiva, idade</p>
                </button>
                <button onClick={() => setCriterio("ESPECIFICO")}
                  className={`text-left px-3 py-2.5 rounded-lg border transition-all ${criterio === "ESPECIFICO" ? "bg-success/15 border-success text-fg-strong" : "bg-bg-dark border-border-dark text-fg-muted hover:border-success/40"}`}>
                  <p className="text-xs font-bold flex items-center gap-1.5"><span className="material-symbols-outlined text-[15px]">workspace_premium</span>Padrão Petrobras</p>
                  <p className="text-[10px] text-fg-faint mt-0.5">Só conhecimento específico · desempate: Português → Inglês</p>
                </button>
              </div>
              {criterio === "ESPECIFICO" && (
                <Field label="Máx. da prova específica (= 100%)">
                  <div className="flex items-center gap-2">
                    <Stepper value={maxEsp} onChange={setMaxEsp} min={1} max={1000} />
                  </div>
                  <p className="text-[10px] text-fg-faint mt-1">ex: Caixa Econômica = 40 pts → 40 = 100%</p>
                </Field>
              )}
            </Section>

            <Section icon="balance" title="Cotas legais">
              <div className="flex items-center justify-between mb-1">
                <span className="text-[10px] uppercase tracking-wider text-fg-faint">Percentual por grupo (%)</span>
                <button onClick={() => setPct({ pn: 25, pi: 3, pq: 2, pcd: 5 })} className="text-[10px] text-primary hover:underline">Lei 15.142/25</button>
              </div>
              <div className="grid grid-cols-2 gap-2">
                {([["pn", "Negros"], ["pi", "Indíg."], ["pq", "Quilom."], ["pcd", "PcD"]] as const).map(([k, lbl]) => (
                  <div key={k} className="flex items-center gap-2 bg-bg-dark border border-border-dark rounded-lg px-2 py-1.5">
                    <span className="text-[11px] text-fg-muted flex-1">{lbl}</span>
                    <input type="number" value={pct[k]} min={0} max={50} step={0.5}
                      onChange={(e) => setPct((p) => ({ ...p, [k]: parseFloat(e.target.value) || 0 }))}
                      className="cc-num w-12 bg-transparent text-right text-sm font-bold text-fg-strong outline-none" />
                    <span className="text-[10px] text-fg-faint">%</span>
                  </div>
                ))}
              </div>
              <Field label="Arredondamento étnico-racial">
                <Select value={arredRacial} onChange={setArredRacial}
                  options={["MEIO", "CIMA", "BAIXO"]}
                  labels={{ MEIO: "Fração ≥ 0,5 sobe (lei)", CIMA: "Sempre para cima", BAIXO: "Sempre para baixo" }} />
              </Field>
            </Section>

            <Section icon="person_search" title="Sua simulação (e se?)">
              <Field label={criterio === "ESPECIFICO" ? `Sua nota específica (de ${maxEsp})` : "Sua pontuação"}>
                <input type="number" value={minhaPont} onChange={(e) => setMinhaPont(e.target.value)} placeholder={criterio === "ESPECIFICO" ? "ex: 37" : "ex: 58"}
                  className="cc-num w-full px-3 py-2 bg-bg-dark border border-border-dark rounded-lg text-sm text-fg-strong placeholder:text-fg-faint focus:ring-1 focus:ring-primary focus:border-primary" />
              </Field>
              <Field label="Suas cotas (pode marcar várias)">
                <div className="flex flex-wrap gap-1.5">
                  <span className="text-[11px] font-medium px-2.5 py-1 rounded-full border border-primary/40 bg-primary/10 text-primary flex items-center gap-1">
                    <span className="material-symbols-outlined text-[13px]">check</span>Ampla (sempre)
                  </span>
                  {(["PN", "PI", "PQ", "PCD"] as const).map((c) => {
                    const on = minhasCats.includes(c);
                    return (
                      <button key={c} onClick={() => toggleCat(c)}
                        className={`text-[11px] font-medium px-2.5 py-1 rounded-full border transition-all ${on ? `${MOD[c].bg} ${MOD[c].text} border-current` : "border-border-dark text-fg-muted hover:border-primary/50"}`}>
                        {on && <span className="material-symbols-outlined text-[13px] mr-0.5 align-middle">check</span>}
                        {MOD[c].curto}
                      </button>
                    );
                  })}
                </div>
                <p className="text-[10px] text-fg-faint mt-1.5">
                  Acumula: ex. <strong className="text-fg-muted">PcD + Negro</strong> concorre nas duas listas + ampla. Entre cotas raciais, na prática vale a de maior % — aqui mostramos todas p/ comparar.
                </p>
              </Field>
            </Section>
          </aside>

          {/* Resultados */}
          <div className="flex-1 min-w-0 p-4 md:p-6 space-y-6">
            {!result ? (
              <div className="flex items-center justify-center h-64 text-fg-faint gap-2">
                <div className="h-5 w-5 border-2 border-primary/30 border-t-primary rounded-full animate-spin" /> Calculando…
              </div>
            ) : (
              <>
                {/* Resumo do recorte */}
                <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-fg-muted cc-reveal">
                  <Badge icon="filter_alt" text={result.recorte.abrangencia === "GERAL" ? "Nacional" : `${result.recorte.abrangencia === "POLO" ? "Estado" : "Região"}: ${result.recorte.valor}`} />
                  <Badge icon="group" text={`${result.recorte.total_no_recorte.toLocaleString("pt-BR")} candidatos no recorte`} />
                  <Badge icon="event_seat" text={`${d!.total} vagas · ${d!.reservadas} reservadas (${d!.pct_reservado}%)`} />
                  {simLoading && <span className="text-primary flex items-center gap-1"><div className="h-3 w-3 border-2 border-primary/30 border-t-primary rounded-full animate-spin" />atualizando</span>}
                </div>

                {/* Sua posição */}
                {result.pessoal && <SuaPosicao p={result.pessoal} />}

                {/* Notas de corte */}
                <div>
                  <SectionTitle icon="trending_down" title="Nota de corte por modalidade" sub={`${result.criterio === "ESPECIFICO" ? `conhecimento específico (máx. ${result.max_esp}) · desempate Port.→Ing.` : "pontos totais"} · CR ${fatorCR}×`} />
                  <div className="grid grid-cols-2 lg:grid-cols-3 xl:grid-cols-5 gap-3">
                    {ORDER.map((m, i) => (
                      <CorteCard key={m} mod={m} result={result} i={i} />
                    ))}
                  </div>
                </div>

                {/* Distribuição */}
                <Distribuicao d={d!} />

                {/* Regra do deslocamento */}
                <Deslocamento result={result} />

                {/* Classificação */}
                <Classificacao result={result} minhaPont={minhaPont} />

                {/* Legislação */}
                <div className="bg-surface-dark border border-border-dark rounded-xl overflow-hidden">
                  <button onClick={() => setShowLei(!showLei)} className="w-full flex items-center justify-between px-5 py-4 hover:bg-white/5 transition-colors">
                    <span className="flex items-center gap-2 text-sm font-semibold text-fg-strong">
                      <span className="material-symbols-outlined text-primary text-[20px]">gavel</span>
                      Base legal das cotas (2025)
                    </span>
                    <span className={`material-symbols-outlined text-fg-faint transition-transform ${showLei ? "rotate-180" : ""}`}>expand_more</span>
                  </button>
                  {showLei && (
                    <div className="px-5 pb-5 text-sm text-fg-muted space-y-2 border-t border-border-dark pt-4">
                      <p><strong className="text-fg">Lei 15.142/2025</strong> + Decreto 12.536/2025 (substituiu a Lei 12.990/2014): reserva total de <strong className="text-warning">30%</strong> étnico-racial → <strong>25%</strong> pretos/pardos, <strong>3%</strong> indígenas, <strong>2%</strong> quilombolas.</p>
                      <p><strong className="text-fg">Decreto 9.508/2018</strong> / Lei 8.112/90: PcD <strong className="text-primary">mín. 5%</strong> (até 20%), apurado em separado.</p>
                      <p><strong className="text-fg">Deslocamento:</strong> todo cotista também concorre na ampla; se classificado dentro das vagas da ampla, <strong>não ocupa</strong> vaga reservada — a fila da cota sobe e outro cotista é convocado.</p>
                      <p><strong className="text-fg">Acúmulo:</strong> quem se enquadra em mais de uma categoria concorre na de maior percentual (negro &gt; indígena &gt; quilombola).</p>
                      <p className="text-xs text-fg-faint pt-1">Simulação educativa. O desempate exato (idade, notas específicas) e regras de alternância de nomeação variam conforme o edital.</p>
                    </div>
                  )}
                </div>
              </>
            )}
          </div>
        </div>
      </main>
    </>
  );
}

// ─── Sub-componentes ─────────────────────────────────────

function ListaConcursos({ icon, titulo, vazio, itens, onOpen, onDelete, deletingId }: {
  icon: string;
  titulo: string;
  vazio: string;
  itens: ConcursoItem[];
  onOpen: (id: number) => void;
  onDelete: (c: ConcursoItem) => void;
  deletingId: number | null;
}) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-4">
        <span className="material-symbols-outlined text-fg-faint text-[20px]">{icon}</span>
        <h3 className="text-sm font-semibold text-fg uppercase tracking-wider">{titulo}</h3>
      </div>
      <div className="space-y-2">
        {itens.length === 0 ? (
          <p className="text-sm text-fg-faint py-6 text-center border border-dashed border-border-dark rounded-xl">{vazio}</p>
        ) : itens.map((c) => (
          <div key={c.id} className="group flex items-center justify-between bg-surface-dark border border-border-dark rounded-xl px-5 py-4 hover:border-primary/50 transition-all">
            <button onClick={() => onOpen(c.id)} className="flex items-center gap-4 text-left flex-1 min-w-0">
              <div className="h-10 w-10 rounded-lg bg-primary/10 flex items-center justify-center text-primary shrink-0">
                <span className="material-symbols-outlined">leaderboard</span>
              </div>
              <div className="min-w-0">
                <p className="text-sm font-semibold text-fg-strong truncate group-hover:text-primary transition-colors">{c.nome}</p>
                <p className="text-xs text-fg-faint cc-num">{c.total_candidatos.toLocaleString("pt-BR")} candidatos</p>
              </div>
            </button>
            {c.publico && c.meu && (
              <span className="hidden sm:inline text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full bg-primary/10 text-primary shrink-0 mr-1">
                seu import
              </span>
            )}
            {c.pode_excluir && (
              <button
                onClick={() => {
                  if (confirm(`Excluir "${c.nome}"?${c.publico ? " Ele sairá do catálogo de todos os usuários." : ""}`)) {
                    onDelete(c);
                  }
                }}
                disabled={deletingId === c.id}
                className="text-fg-faint hover:text-accent-error transition-colors p-2 disabled:opacity-50"
              >
                <span className="material-symbols-outlined text-[20px]">delete</span>
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

function PageHeader({ children }: { children?: React.ReactNode }) {
  return (
    <header className="sticky top-0 z-30 bg-bg-dark/80 backdrop-blur-md border-b border-border-dark px-4 md:px-8 py-4 flex items-center gap-4">
      {children || (
        <h1 className="text-xl font-bold text-fg-strong flex items-center gap-2">
          <span className="material-symbols-outlined text-primary">leaderboard</span>
          Concorrência
        </h1>
      )}
    </header>
  );
}

function Section({ icon, title, children }: { icon: string; title: string; children: React.ReactNode }) {
  return (
    <div>
      <h3 className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-wider text-fg-muted mb-3">
        <span className="material-symbols-outlined text-primary text-[16px]">{icon}</span>{title}
      </h3>
      <div className="space-y-3">{children}</div>
    </div>
  );
}

function SectionTitle({ icon, title, sub }: { icon: string; title: string; sub?: string }) {
  return (
    <div className="flex items-baseline gap-3 mb-3">
      <h3 className="flex items-center gap-2 text-sm font-bold text-fg-strong">
        <span className="material-symbols-outlined text-primary text-[18px]">{icon}</span>{title}
      </h3>
      {sub && <span className="text-[11px] text-fg-faint">{sub}</span>}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-[10px] font-semibold text-fg-faint uppercase tracking-wider mb-1.5">{label}</label>
      {children}
    </div>
  );
}

function Select({ value, onChange, options, labels }: { value: string; onChange: (v: string) => void; options: string[]; labels?: Record<string, string> }) {
  return (
    <select value={value} onChange={(e) => onChange(e.target.value)}
      className="w-full px-3 py-2 bg-bg-dark border border-border-dark rounded-lg text-sm text-fg-strong focus:ring-1 focus:ring-primary focus:border-primary appearance-none cursor-pointer">
      {options.map((o) => <option key={o} value={o}>{labels?.[o] || o}</option>)}
    </select>
  );
}

function Stepper({ value, onChange, min, max }: { value: number; onChange: (v: number) => void; min: number; max: number }) {
  const set = (v: number) => onChange(Math.max(min, Math.min(max, v)));
  return (
    <div className="flex items-center bg-bg-dark border border-border-dark rounded-lg overflow-hidden">
      <button onClick={() => set(value - 1)} className="px-3 py-2 text-fg-muted hover:text-fg-strong hover:bg-white/5 transition-colors">−</button>
      <input type="number" value={value} onChange={(e) => set(parseInt(e.target.value) || min)}
        className="cc-num flex-1 min-w-0 bg-transparent text-center text-lg font-bold text-fg-strong outline-none py-1.5" />
      <button onClick={() => set(value + 1)} className="px-3 py-2 text-fg-muted hover:text-fg-strong hover:bg-white/5 transition-colors">+</button>
    </div>
  );
}

function Badge({ icon, text }: { icon: string; text: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="material-symbols-outlined text-[15px] text-fg-faint">{icon}</span>{text}
    </span>
  );
}

function CorteCard({ mod, result, i }: { mod: Mod; result: SimResult; i: number }) {
  const c = MOD[mod];
  const corte = result.nota_corte[mod];
  const pct = result.nota_corte_pct?.[mod];
  const vagas = result.distribuicao.vagas[mod];
  const conv = result.distribuicao.convocados[mod];
  const g = mod !== "AC" ? result.grupos[mod] : null;
  const inativa = mod !== "AC" && vagas === 0;

  return (
    <div style={{ animationDelay: `${i * 50}ms` }}
      className={`cc-reveal rounded-xl border border-border-dark ${c.bg} ring-1 ${inativa ? "ring-border-dark opacity-50" : c.ring} p-4 flex flex-col gap-2`}>
      <div className="flex items-center justify-between">
        <span className={`flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wide ${c.text}`}>
          <span className="material-symbols-outlined text-[15px]">{c.icon}</span>{c.curto}
        </span>
        <span className="cc-num text-[10px] text-fg-faint">{vagas}v · {conv} conv.</span>
      </div>
      <div>
        <p className="cc-num text-3xl font-extrabold text-fg-strong leading-none">
          {corte != null ? corte.toLocaleString("pt-BR") : <span className="text-fg-faint text-xl">—</span>}
          {corte != null && pct != null && (
            <span className="text-sm font-bold text-success ml-1.5">{pct.toLocaleString("pt-BR")}%</span>
          )}
        </p>
        <p className="text-[10px] text-fg-faint mt-1">{c.nome}</p>
      </div>
      {g && !inativa && (
        <div className="text-[10px] text-fg-faint border-t border-white/5 pt-2 cc-num">
          {g.total_inscritos} inscritos · {g.preenchidas} convocados
        </div>
      )}
      {inativa && <div className="text-[10px] text-fg-faint border-t border-white/5 pt-2">Sem vaga neste recorte</div>}
    </div>
  );
}

function Distribuicao({ d }: { d: SimResult["distribuicao"] }) {
  const total = d.total || 1;
  const segs = ORDER.filter((m) => d.vagas[m] > 0);
  return (
    <div className="bg-surface-dark border border-border-dark rounded-xl p-5 cc-reveal">
      <SectionTitle icon="pie_chart" title="Distribuição das vagas" sub={`${d.total} vagas imediatas · CR ${d.fator_cr}×`} />
      <div className="flex h-4 rounded-full overflow-hidden bg-bg-dark mb-4">
        {segs.map((m) => (
          <div key={m} className={`${MOD[m].bar} transition-all`} style={{ width: `${(d.vagas[m] / total) * 100}%` }} title={`${MOD[m].nome}: ${d.vagas[m]}`} />
        ))}
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {ORDER.map((m) => (
          <div key={m} className="flex items-center gap-2">
            <span className={`h-3 w-3 rounded-sm ${MOD[m].bar} ${d.vagas[m] === 0 ? "opacity-30" : ""}`} />
            <div>
              <p className="text-[11px] text-fg-muted">{MOD[m].curto}</p>
              <p className="cc-num text-sm font-bold text-fg-strong">{d.vagas[m]} <span className="text-[10px] font-normal text-fg-faint">/ {d.convocados[m]} CR</span></p>
            </div>
          </div>
        ))}
      </div>
      {!d.aplica_racial && (
        <p className="text-[11px] text-warning/80 mt-3 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-[14px]">info</span>
          Reserva étnico-racial não se aplica: total de vagas abaixo do limiar legal.
        </p>
      )}
    </div>
  );
}

function Deslocamento({ result }: { result: SimResult }) {
  const grupos = (["PN", "PI", "PQ", "PCD"] as Mod[]).map((m) => result.grupos[m]).filter((g) => g && g.total_inscritos > 0);
  const totalDesloc = grupos.reduce((s, g) => s + g.deslocados_ampla, 0);
  return (
    <div className="bg-gradient-to-br from-primary/10 to-transparent border border-primary/20 rounded-xl p-5 cc-reveal">
      <SectionTitle icon="swap_vert" title="Regra do deslocamento (a fila sobe)" />
      <p className="text-sm text-fg-muted mb-4">
        <strong className="cc-num text-primary">{totalDesloc}</strong> cotista(s) foram classificados <strong className="text-fg-strong">dentro das vagas da ampla concorrência</strong>.
        Pela Lei 15.142/2025, eles assumem a vaga de ampla e <strong className="text-fg-strong">não ocupam</strong> a vaga reservada — então a fila da cota sobe e outro candidato é convocado no lugar.
      </p>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {grupos.map((g) => (
          <div key={g.sigla} className="bg-bg-dark/60 border border-border-dark rounded-lg p-3">
            <p className={`text-[11px] font-bold uppercase ${MOD[g.sigla].text} mb-1`}>{MOD[g.sigla].curto}</p>
            <p className="cc-num text-2xl font-extrabold text-fg-strong">{g.deslocados_ampla}</p>
            <p className="text-[10px] text-fg-faint mt-0.5">passaram na ampla · {g.concorrem_reserva} disputam a reserva</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function SuaPosicao({ p }: { p: NonNullable<SimResult["pessoal"]> }) {
  const cats = p.categorias_info || [];
  const esp = p.criterio === "ESPECIFICO";
  const pctOf = (v: number | null) => (esp && v != null && p.max_esp > 0 ? +(v / p.max_esp * 100).toFixed(1) : null);
  const catPassa = cats.find((c) => c.passa);
  const melhorSigla: Mod | null = p.passa_ac ? "AC" : catPassa ? catPassa.sigla : null;
  return (
    <div className="bg-surface-dark border-2 border-primary/40 rounded-xl p-5 cc-reveal">
      <SectionTitle icon="my_location" title="Sua posição estimada"
        sub={esp ? `nota específica ${p.pontuacao}${p.pontuacao_pct != null ? ` (${p.pontuacao_pct}%)` : ""}` : `pontuação ${p.pontuacao}`} />
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <PosBox titulo="Ampla Concorrência" pos={p.posicao_ac} conv={p.convocados_ac} passa={p.passa_ac} corte={p.nota_corte_ac} cortePct={pctOf(p.nota_corte_ac)} falta={p.falta_ac} mod="AC" />
        {cats.map((ci) => (
          <PosBox key={ci.sigla} titulo={ci.nome} pos={ci.posicao} conv={ci.convocados} passa={ci.passa} corte={ci.nota_corte} cortePct={pctOf(ci.nota_corte)} falta={ci.falta} mod={ci.sigla} />
        ))}
        {cats.length === 0 && (
          <div className="flex items-center justify-center text-xs text-fg-faint border border-dashed border-border-dark rounded-lg p-4 sm:col-span-1">
            Marque suas cotas no painel (pode acumular) para comparar cada lista.
          </div>
        )}
      </div>
      <p className="text-[11px] text-fg-faint mt-3 flex items-center gap-1.5">
        <span className="material-symbols-outlined text-[14px] text-primary">tips_and_updates</span>
        {melhorSigla
          ? <>Você seria <strong className="text-accent-success">convocado</strong> {melhorSigla === "AC" ? "pela ampla concorrência" : `pela lista ${MOD[melhorSigla].nome}`} — basta passar em <strong>uma</strong> das listas.</>
          : <>Com essa pontuação você ainda <strong className="text-accent-error">não seria convocado</strong> em nenhuma das suas listas.</>}
      </p>
    </div>
  );
}

function PosBox({ titulo, pos, conv, passa, corte, cortePct, falta, mod }: { titulo: string; pos: number; conv: number; passa: boolean; corte: number | null; cortePct?: number | null; falta: number; mod: Mod }) {
  return (
    <div className={`relative rounded-lg p-4 ${MOD[mod].bg} border transition-all ${passa ? "border-accent-success/60 ring-1 ring-accent-success/40 shadow-lg shadow-accent-success/10" : "border-border-dark"}`}>
      <div className="flex items-center justify-between mb-2 gap-2">
        <span className={`text-[11px] font-bold uppercase ${MOD[mod].text}`}>{titulo}</span>
        {passa ? (
          <span className="flex items-center gap-1 text-[11px] font-bold px-2 py-0.5 rounded-full bg-accent-success/20 text-accent-success">
            <span className="material-symbols-outlined text-[14px]">emoji_events</span>CONVOCADO
          </span>
        ) : (
          <span className="text-[11px] font-bold px-2 py-0.5 rounded-full bg-accent-error/20 text-accent-error">Fora</span>
        )}
      </div>
      <p className="cc-num text-3xl font-extrabold text-fg-strong flex items-center gap-1.5">
        {passa && <span className="material-symbols-outlined text-accent-success text-[26px]">emoji_events</span>}
        {pos}º <span className="text-sm font-normal text-fg-faint">/ {conv} conv.</span>
      </p>
      <p className="cc-num text-[11px] text-fg-faint mt-1">
        Corte: {corte != null ? corte : "—"}{cortePct != null && <span className="text-success"> ({cortePct}%)</span>}
        {!passa && falta > 0 && <span className="text-warning"> · faltam {falta} pts</span>}
      </p>
    </div>
  );
}

function Classificacao({ result, minhaPont }: { result: SimResult; minhaPont: string }) {
  const [q, setQ] = useState("");
  const mp = minhaPont ? parseFloat(minhaPont) : null;
  const rows = result.classificacao.filter((r) => !q || r.inscricao.includes(q) || r.polo.includes(q.toUpperCase()));

  const esp = result.criterio === "ESPECIFICO";
  const tags = (r: ClassRow) => {
    const t: Mod[] = [];
    if (r.is_negro) t.push("PN");
    if (r.is_indigena) t.push("PI");
    if (r.is_quilombola) t.push("PQ");
    if (r.is_pcd) t.push("PCD");
    return t;
  };

  return (
    <div className="bg-surface-dark border border-border-dark rounded-xl overflow-hidden cc-reveal">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-5 border-b border-border-dark">
        <SectionTitle icon="format_list_numbered" title="Lista de classificação" sub={`top ${result.classificacao.length} de ${result.classificacao_total.toLocaleString("pt-BR")}`} />
        <div className="relative">
          <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-fg-faint text-[18px]">search</span>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="inscrição ou UF"
            className="pl-8 pr-3 py-1.5 bg-bg-dark border border-border-dark rounded-lg text-xs text-fg-strong placeholder:text-fg-faint focus:ring-1 focus:ring-primary w-full sm:w-48" />
        </div>
      </div>
      <div className="overflow-x-auto max-h-[560px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface-dark z-10">
            <tr className="text-[10px] uppercase tracking-wider text-fg-faint border-b border-border-dark">
              <th className="text-left font-semibold px-4 py-2.5 w-16">#</th>
              <th className="text-left font-semibold px-3 py-2.5">Inscrição</th>
              <th className="text-left font-semibold px-3 py-2.5">UF</th>
              <th className="text-right font-semibold px-3 py-2.5">{esp ? "Específica" : "Pontos"}</th>
              {esp && <th className="text-right font-semibold px-3 py-2.5">Total</th>}
              <th className="text-left font-semibold px-3 py-2.5">Cotas</th>
              <th className="text-left font-semibold px-4 py-2.5">Entrou por</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => {
              const mine = mp != null && r.nota === mp;
              return (
                <tr key={r.inscricao + r.rank_geral}
                  className={`border-b border-border-dark/50 transition-colors ${mine ? "bg-primary/10" : "hover:bg-white/[0.03]"}`}>
                  <td className="px-4 py-2 cc-num text-fg-faint">{r.rank_geral}</td>
                  <td className="px-3 py-2 cc-num text-fg">{r.inscricao}</td>
                  <td className="px-3 py-2 text-fg-muted">{r.polo}</td>
                  <td className="px-3 py-2 cc-num text-right font-bold text-fg-strong">
                    {r.nota}
                    {esp && r.nota_pct != null && <span className="text-[10px] font-medium text-success ml-1">{r.nota_pct}%</span>}
                  </td>
                  {esp && <td className="px-3 py-2 cc-num text-right text-fg-faint">{r.pontos}</td>}
                  <td className="px-3 py-2">
                    <div className="flex gap-1">
                      {tags(r).map((t) => (
                        <span key={t} className={`text-[9px] font-bold px-1.5 py-0.5 rounded ${MOD[t].bg} ${MOD[t].text}`}>{MOD[t].curto}</span>
                      ))}
                    </div>
                  </td>
                  <td className="px-4 py-2">
                    {r.entrou_por ? (
                      <span className={`inline-flex items-center gap-1 text-[10px] font-bold px-2 py-0.5 rounded-full ${MOD[r.entrou_por].bg} ${MOD[r.entrou_por].text}`}>
                        <span className="material-symbols-outlined text-[12px]">{MOD[r.entrou_por].icon}</span>
                        {MOD[r.entrou_por].curto}
                      </span>
                    ) : (
                      <span className="text-[10px] text-fg-faint">fora do CR</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

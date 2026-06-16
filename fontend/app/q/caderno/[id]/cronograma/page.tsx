"use client";
import { useEffect, useRef, useState, useCallback, useMemo } from "react";
import { useParams } from "next/navigation";
import { apiFetch } from "@/lib/api";
import {
  getCronograma, criarCronograma, recalcular,
  type CronogramaResp, type CronogramaInput,
} from "./api";
import { ConfigForm } from "./components/ConfigForm";
import { KpiStrip } from "./components/KpiStrip";
import { TimelineTable } from "./components/TimelineTable";
import { RevisarHoje } from "./components/RevisarHoje";
import { DiscursivasList } from "./components/DiscursivasList";
import { SimuladosList } from "./components/SimuladosList";

export default function CronogramaPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<CronogramaResp | null>(null);
  const [loading, setLoading] = useState(true);
  // Contador de reloads para forçar re-fetch sem alterar deps do effect
  const [reloadKey, setReloadKey] = useState(0);
  const loadingRef = useRef(false);

  // useMemo deve ficar antes de qualquer early return
  const diasAteProva = useMemo(() => {
    if (!data) return 0;
    const agora = new Date();
    agora.setHours(0, 0, 0, 0);
    return Math.max(0, Math.ceil((+new Date(data.config.data_prova) - +agora) / 86400000));
  }, [data]);

  useEffect(() => {
    let cancelled = false;
    loadingRef.current = true;

    getCronograma(id).then((resp) => {
      if (cancelled) return;
      setData(resp);
      setLoading(false);
      loadingRef.current = false;
    }).catch(() => {
      if (cancelled) return;
      setLoading(false);
      loadingRef.current = false;
    });

    return () => { cancelled = true; };
  }, [id, reloadKey]);

  const load = useCallback(() => {
    setLoading(true);
    setReloadKey((k) => k + 1);
  }, []);

  async function onCreate(input: CronogramaInput) {
    const resp = await criarCronograma(id, input);
    setData(resp);
  }

  async function baixarXlsx() {
    const r = await apiFetch(`/api/q/cadernos/${id}/cronograma/export.xlsx`);
    const blob = await r.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = `cronograma_${id}.xlsx`; a.click();
    URL.revokeObjectURL(url);
  }

  if (loading) return <div className="p-6 text-fg-muted">Carregando…</div>;
  if (!data) {
    return (
      <div className="p-6">
        <h1 className="text-xl font-semibold mb-4">Criar cronograma</h1>
        <ConfigForm submitLabel="Gerar cronograma" onSubmit={onCreate} />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Cronograma</h1>
        <div className="flex gap-2">
          <button onClick={() => recalcular(id).then(setData)}
            className="text-sm border border-border/60 rounded px-3 py-1.5">Recalcular automático</button>
          <button onClick={baixarXlsx}
            className="text-sm bg-primary text-black font-semibold rounded px-3 py-1.5">Baixar .xlsx</button>
        </div>
      </div>
      <KpiStrip kpis={data.kpis} diasAteProva={diasAteProva} />
      <section><h2 className="text-sm font-semibold mb-2 text-fg-muted">Plano diário</h2>
        <TimelineTable plano={data.plano} /></section>
      {data.config.incluir_revisao && (
        <section><h2 className="text-sm font-semibold mb-2 text-fg-muted">Revisar hoje</h2>
          <RevisarHoje itens={data.revisar_hoje} /></section>)}
      {data.config.incluir_discursivas && (
        <section><h2 className="text-sm font-semibold mb-2 text-fg-muted">Discursivas</h2>
          <DiscursivasList id={id} itens={data.discursivas} onChange={load} /></section>)}
      {data.config.incluir_simulados && (
        <section><h2 className="text-sm font-semibold mb-2 text-fg-muted">Simulados</h2>
          <SimuladosList id={id} itens={data.simulados} onChange={load} /></section>)}
    </div>
  );
}

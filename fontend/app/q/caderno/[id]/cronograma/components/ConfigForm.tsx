"use client";
import { useState } from "react";
import type { CronogramaInput } from "../api";

const DIAS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]; // index = weekday (0..6)

export function ConfigForm({
  initial,
  submitLabel,
  onSubmit,
}: {
  initial?: Partial<CronogramaInput>;
  submitLabel: string;
  onSubmit: (input: CronogramaInput) => Promise<void>;
}) {
  const hoje = new Date().toISOString().slice(0, 10);
  const [dataInicio, setDataInicio] = useState(initial?.data_inicio ?? hoje);
  const [dataProva, setDataProva] = useState(initial?.data_prova ?? "");
  const [folga, setFolga] = useState<number[]>(initial?.dias_folga ?? [6]);
  const [buffer, setBuffer] = useState(initial?.buffer_dias ?? 21);
  const [discursivas, setDiscursivas] = useState(
    initial?.incluir_discursivas ?? false
  );
  const [simulados, setSimulados] = useState(
    initial?.incluir_simulados ?? true
  );
  const [revisao, setRevisao] = useState(initial?.incluir_revisao ?? true);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const toggleDia = (w: number) =>
    setFolga((f) =>
      f.includes(w) ? f.filter((x) => x !== w) : [...f, w]
    );

  async function submit() {
    setErr("");
    if (!dataProva) {
      setErr("Informe a data da prova.");
      return;
    }
    if (dataProva <= dataInicio) {
      setErr("A prova deve ser depois do início.");
      return;
    }
    setBusy(true);
    try {
      await onSubmit({
        data_prova: dataProva,
        data_inicio: dataInicio,
        dias_folga: folga,
        buffer_dias: buffer,
        incluir_revisao: revisao,
        incluir_discursivas: discursivas,
        incluir_simulados: simulados,
        discursivas_por_semana: 2,
      });
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Erro");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-lg mx-auto bg-surface border border-border/60 rounded-lg p-6 space-y-4">
      <h2 className="text-lg font-semibold text-fg">Configurar cronograma</h2>

      <label className="block text-sm">
        Data da prova
        <input
          type="date"
          value={dataProva}
          onChange={(e) => setDataProva(e.target.value)}
          className="mt-1 w-full bg-surface-2 border border-border/60 rounded px-3 py-2"
        />
      </label>

      <label className="block text-sm">
        Início
        <input
          type="date"
          value={dataInicio}
          onChange={(e) => setDataInicio(e.target.value)}
          className="mt-1 w-full bg-surface-2 border border-border/60 rounded px-3 py-2"
        />
      </label>

      <div className="text-sm">
        <span className="block mb-1">Dias de folga (reservados)</span>
        <div className="flex gap-1">
          {DIAS.map((d, w) => (
            <button
              key={w}
              type="button"
              onClick={() => toggleDia(w)}
              className={`px-2 py-1 rounded text-xs border ${
                folga.includes(w)
                  ? "bg-primary/10 border-primary/40 text-primary"
                  : "bg-surface-2 border-border/60 text-fg-muted"
              }`}
            >
              {d}
            </button>
          ))}
        </div>
        <p className="text-xs text-fg-faint mt-1">
          Sábado fica como dia de estudo por padrão; marque para reservar.
        </p>
      </div>

      <label className="block text-sm">
        Buffer de reta final (dias)
        <input
          type="number"
          min={0}
          max={120}
          value={buffer}
          onChange={(e) => setBuffer(Number(e.target.value))}
          className="mt-1 w-full bg-surface-2 border border-border/60 rounded px-3 py-2"
        />
      </label>

      <div className="space-y-1 text-sm">
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={revisao}
            onChange={(e) => setRevisao(e.target.checked)}
          />
          Revisão espaçada das erradas
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={discursivas}
            onChange={(e) => setDiscursivas(e.target.checked)}
          />
          Discursivas (temas via IA)
        </label>
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={simulados}
            onChange={(e) => setSimulados(e.target.checked)}
          />
          Simulados
        </label>
      </div>

      {err && <p className="text-error text-sm">{err}</p>}

      <button
        onClick={submit}
        disabled={busy}
        className="w-full bg-primary text-black font-semibold rounded py-2 disabled:opacity-50"
      >
        {busy ? "Gerando…" : submitLabel}
      </button>
    </div>
  );
}

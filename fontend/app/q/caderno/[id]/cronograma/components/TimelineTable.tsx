"use client";
import type { DiaPlano } from "../api";

const FASE: Record<string, string> = {
  "1volta": "1ª volta", folga: "Folga", buffer: "Buffer", prova: "PROVA",
};

export function TimelineTable({ plano }: { plano: DiaPlano[] }) {
  return (
    <div className="overflow-auto max-h-[480px] border border-border/60 rounded-lg">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-surface-2 text-fg-muted text-xs">
          <tr>
            {["Data", "Fase", "Meta dia", "Meta acum."].map((h) => (
              <th key={h} className="text-left px-3 py-2 font-medium">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {plano.map((d) => (
            <tr key={d.data} className={`border-t border-border/40 ${d.hoje ? "bg-primary/10" : ""}`}>
              <td className="px-3 py-1.5">{d.data.slice(5)}{d.hoje && " ◀ hoje"}</td>
              <td className="px-3 py-1.5 text-fg-muted">{FASE[d.fase] ?? d.fase}</td>
              <td className="px-3 py-1.5">{d.questoes_novas || "—"}</td>
              <td className="px-3 py-1.5">{d.meta_acumulada}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

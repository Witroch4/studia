"use client";
import type { Simulado } from "../api";
import { patchSimulado } from "../api";
export function SimuladosList({ id, itens, onChange }:
  { id: string; itens: Simulado[]; onChange: () => void }) {
  if (!itens.length) return <p className="text-sm text-fg-faint">Sem simulados.</p>;
  return (
    <table className="w-full text-sm">
      <thead className="text-fg-muted text-xs">
        <tr><th className="text-left py-1">Data</th><th className="text-left">Tipo</th>
        <th className="text-left">Meta</th><th className="text-left">Resultado</th></tr>
      </thead>
      <tbody>
        {itens.map((s) => (
          <tr key={s.id} className="border-t border-border/40">
            <td className="py-1">{s.data.slice(5)}</td>
            <td>{s.tipo}</td>
            <td>{s.meta_objetiva}</td>
            <td>
              <input type="number" defaultValue={s.resultado_objetiva ?? ""}
                onBlur={async (e) => { await patchSimulado(id, s.id, { resultado_objetiva: e.target.value ? Number(e.target.value) : null }); onChange(); }}
                className="w-16 bg-surface-2 border border-border/60 rounded px-1" />
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

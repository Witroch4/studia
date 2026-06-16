"use client";
import { useState } from "react";
import type { Discursiva } from "../api";
import { patchDiscursiva, regenerarDiscursivas } from "../api";

const STATUS = ["Pendente", "Feita", "Rever", "Reescrita"];

export function DiscursivasList({ id, itens, onChange }:
  { id: string; itens: Discursiva[]; onChange: () => void }) {
  const [busy, setBusy] = useState(false);
  if (!itens.length) {
    return (
      <button disabled={busy} onClick={async () => { setBusy(true); await regenerarDiscursivas(id); onChange(); setBusy(false); }}
        className="text-sm text-primary">{busy ? "Gerando temas…" : "Gerar temas por IA"}</button>
    );
  }
  return (
    <div className="space-y-2">
      {itens.map((d) => (
        <div key={d.id} className="bg-surface border border-border/60 rounded px-3 py-2 text-sm">
          <div className="flex justify-between gap-2">
            <span className="text-fg-faint">{d.data.slice(5)}</span>
            <select defaultValue={d.status}
              onChange={async (e) => { await patchDiscursiva(id, d.id, { status: e.target.value }); onChange(); }}
              className="bg-surface-2 border border-border/60 rounded text-xs px-1">
              {STATUS.map((s) => <option key={s}>{s}</option>)}
            </select>
          </div>
          <p className="mt-1">{d.tema}</p>
        </div>
      ))}
    </div>
  );
}

"use client";

import React from "react";
import { Badge, BadgeTone } from "./Badge";

export type StatusKey =
  | "processando"
  | "ativo"
  | "pendente"
  | "concluido"
  | "erro"
  | "cancelado"
  | "inativo";

const STATUS: Record<StatusKey, { tone: BadgeTone; label: string; icon: string }> = {
  processando: { tone: "primary", label: "Processando", icon: "autorenew" },
  ativo: { tone: "primary", label: "Ativo", icon: "bolt" },
  pendente: { tone: "warning", label: "Pendente", icon: "schedule" },
  concluido: { tone: "success", label: "Concluído", icon: "check" },
  erro: { tone: "error", label: "Erro", icon: "error" },
  cancelado: { tone: "neutral", label: "Cancelado", icon: "block" },
  inativo: { tone: "neutral", label: "Inativo", icon: "pause" },
};

export interface StatusBadgeProps {
  status?: StatusKey;
  label?: string;
  showIcon?: boolean;
  size?: "sm" | "md";
}

/**
 * StatusBadge — job / processing status pill with studIA's Portuguese labels
 * and semantic tones baked in. Pass a `status` key; override `label` if needed.
 */
export function StatusBadge({ status = "pendente", label, showIcon = true, size = "md" }: StatusBadgeProps) {
  const cfg = STATUS[status] || STATUS.pendente;
  return (
    <Badge tone={cfg.tone} icon={showIcon ? cfg.icon : undefined} size={size}>
      {label || cfg.label}
    </Badge>
  );
}

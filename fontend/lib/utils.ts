import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

/**
 * Dias até uma data (ISO `YYYY-MM-DD...`). 0 = hoje; negativo = já passou;
 * `null` = sem data ou data inválida. Usado no countdown do Mapa da Aprovação
 * (lista `/q/mapa` e detalhe `/q/mapa/[id]`).
 */
export function diasRestantes(dataIso: string | null): number | null {
  if (!dataIso) return null
  const hoje = new Date()
  hoje.setHours(0, 0, 0, 0)
  const alvo = new Date(`${dataIso.slice(0, 10)}T00:00:00`)
  if (Number.isNaN(alvo.getTime())) return null
  return Math.round((alvo.getTime() - hoje.getTime()) / 86_400_000)
}

/**
 * Helper central de chamadas ao backend FastAPI.
 *
 * `credentials: "include"` é essencial: em dev o front (:3000) e o back (:8011)
 * são cross-origin, então o cookie do Better Auth só viaja com credenciais
 * habilitadas (em prod é same-origin via Traefik e isso é inofensivo).
 */

export const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8011";

export function apiUrl(path: string): string {
  if (/^https?:\/\//.test(path)) return path;
  return `${API_BASE}${path.startsWith("/") ? "" : "/"}${path}`;
}

export class ApiError extends Error {
  status: number;
  data: unknown;
  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
  /** True quando o backend bloqueou por limite diário do plano grátis (402). */
  get isLimite(): boolean {
    const d = this.data as { detail?: { erro?: string } } | undefined;
    return this.status === 402 || d?.detail?.erro === "limite_diario";
  }
}

// ---------------------------------------------------------------------------
// Helpers de CSRF e handoff JWT
// ---------------------------------------------------------------------------

function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : null;
}

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);
let handoffInFlight: Promise<void> | null = null;

export async function ensureHandoff(): Promise<void> {
  if (!handoffInFlight) {
    handoffInFlight = fetch(apiUrl("/api/session/handoff"), {
      method: "POST",
      credentials: "include",
    })
      .then(() => undefined)
      .finally(() => {
        handoffInFlight = null;
      });
  }
  return handoffInFlight;
}

function withCsrf(init: RequestInit): RequestInit {
  const method = (init.method || "GET").toUpperCase();
  if (!MUTATING.has(method)) return init;
  const csrf = readCookie("studia_csrf");
  return {
    ...init,
    headers: { ...(init.headers || {}), ...(csrf ? { "X-CSRF-Token": csrf } : {}) },
  };
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const doFetch = () => fetch(apiUrl(path), { credentials: "include", ...withCsrf(init) });
  let res = await doFetch();
  if (res.status === 401) {
    // JWT ausente/expirado: faz o handoff (mint do JWT) e tenta de novo, uma vez.
    await ensureHandoff();
    res = await doFetch();
  }
  return res;
}

// ---------------------------------------------------------------------------

function extrairMensagem(data: unknown, status: number): string {
  const d = data as
    | { detail?: { mensagem?: string } | string; message?: string }
    | undefined;
  if (d && typeof d.detail === "object" && d.detail?.mensagem) return d.detail.mensagem;
  if (d && typeof d.detail === "string") return d.detail;
  if (d && typeof d.message === "string") return d.message;
  return `HTTP ${status}`;
}

export async function apiJson<T = unknown>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await apiFetch(path, init);
  const text = await res.text();
  let data: unknown = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = text;
  }
  if (!res.ok) {
    throw new ApiError(res.status, extrairMensagem(data, res.status), data);
  }
  return data as T;
}

export function apiPost<T = unknown>(path: string, body?: unknown): Promise<T> {
  return apiJson<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
}

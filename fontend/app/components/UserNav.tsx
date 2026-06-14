"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authClient, useSession } from "@/lib/auth-client";
import { apiFetch, apiJson } from "@/lib/api";

function initialsOf(name?: string | null, email?: string | null) {
  const base = (name || email || "").trim();
  if (!base) return "?";
  const parts = base.split(/\s+/).filter(Boolean);
  if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
  return base.slice(0, 2).toUpperCase();
}

/**
 * Badge de usuário no rodapé da sidebar — substitui o "Engenheiro Jr." fixo.
 * Mostra nome/email reais da sessão Better Auth, role e um menu com
 * "Minha conta" + "Sair" (logout funcional).
 */
export default function UserNav({ variant = "desktop" }: { variant?: "desktop" | "mobile" }) {
  const { data: session, isPending } = useSession();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [plano, setPlano] = useState<"free" | "pro" | null>(null);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!session?.user) return;
    let vivo = true;
    apiJson<{ plano: "free" | "pro" }>("/api/billing/status")
      .then((d) => vivo && setPlano(d.plano))
      .catch(() => {});
    return () => {
      vivo = false;
    };
  }, [session?.user]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  const user = session?.user as
    | { name?: string; email?: string; role?: string }
    | undefined;
  const name = user?.name || "Conta";
  const email = user?.email || "";
  const role = user?.role || "user";
  const initials = isPending ? "··" : initialsOf(user?.name, user?.email);

  async function handleLogout() {
    setLoggingOut(true);
    // Limpa os cookies JWT do backend (studia_session + studia_csrf) antes do signOut.
    // best-effort: falha silenciosa para não bloquear o logout.
    await apiFetch("/api/session/logout", { method: "POST" }).catch(() => {});
    await authClient.signOut();
    router.push("/login");
    router.refresh();
  }

  const Avatar = (
    <div className={`${variant === "mobile" ? "h-10 w-10" : "h-8 w-8"} rounded-full bg-gradient-to-tr from-primary to-secondary p-[1px] flex-shrink-0`}>
      <div className="rounded-full h-full w-full bg-surface-dark flex items-center justify-center">
        <span className="text-xs font-bold text-fg-strong">{initials}</span>
      </div>
    </div>
  );

  // Versão mobile: só o avatar clicável com menu suspenso
  if (variant === "mobile") {
    return (
      <div className="relative" ref={ref}>
        <button onClick={() => setOpen((v) => !v)} className="block rounded-full focus:outline-none focus:ring-2 focus:ring-primary">
          {Avatar}
        </button>
        {open && <Menu name={name} email={email} role={role} plano={plano} onLogout={handleLogout} loggingOut={loggingOut} />}
      </div>
    );
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="sidebar-row w-full flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-fg-strong/6 transition-colors text-left focus:outline-none focus:ring-2 focus:ring-primary/50"
      >
        {Avatar}
        <div className="sidebar-label flex-1 min-w-0">
          <p className="text-sm font-medium text-fg-strong truncate">{name}</p>
          <p className="text-xs text-fg-faint truncate">{email || "—"}</p>
        </div>
        <span className="sidebar-label material-symbols-outlined text-fg-faint text-[18px]">unfold_more</span>
      </button>
      {open && <Menu name={name} email={email} role={role} plano={plano} onLogout={handleLogout} loggingOut={loggingOut} />}
    </div>
  );
}

function Menu({
  name,
  email,
  role,
  plano,
  onLogout,
  loggingOut,
}: {
  name: string;
  email: string;
  role: string;
  plano: "free" | "pro" | null;
  onLogout: () => void;
  loggingOut: boolean;
}) {
  const isAdmin = role === "admin";
  const isPro = isAdmin || plano === "pro";
  return (
    <div className="absolute bottom-full right-0 mb-2 w-60 rounded-xl border border-border-dark bg-surface-dark shadow-xl overflow-hidden z-50 animate-in">
      <div className="px-4 py-3 border-b border-border-dark/60">
        <p className="text-sm font-semibold text-fg-strong truncate">{name}</p>
        <p className="text-xs text-fg-faint truncate">{email}</p>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide"
            style={{
              color: isAdmin ? "var(--color-secondary)" : "var(--color-primary)",
              background: isAdmin ? "rgba(139,92,246,0.12)" : "rgba(6,182,212,0.12)",
            }}>
            <span className="material-symbols-outlined text-[12px]">{isAdmin ? "shield_person" : "person"}</span>
            {role}
          </span>
          {plano && (
            <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide"
              style={{
                color: isPro ? "var(--color-secondary)" : "#9ca3af",
                background: isPro ? "rgba(139,92,246,0.12)" : "rgba(148,163,184,0.12)",
              }}>
              <span className="material-symbols-outlined text-[12px]">{isPro ? "workspace_premium" : "bolt"}</span>
              {isPro ? "Pro" : "Grátis"}
            </span>
          )}
        </div>
      </div>
      <div className="p-1">
        {!isPro && (
          <Link href="/assinar" className="flex items-center gap-3 px-3 py-2 text-sm text-secondary rounded-lg hover:bg-secondary/10 transition-colors font-medium">
            <span className="material-symbols-outlined text-[18px]">workspace_premium</span>
            Assinar Pro
          </Link>
        )}
        <Link href="/conta" className="flex items-center gap-3 px-3 py-2 text-sm text-fg rounded-lg hover:bg-surface-2 hover:text-fg-strong transition-colors">
          <span className="material-symbols-outlined text-[18px] text-primary/70">manage_accounts</span>
          Minha conta
        </Link>
        <button
          onClick={onLogout}
          disabled={loggingOut}
          className="w-full flex items-center gap-3 px-3 py-2 text-sm text-error rounded-lg hover:bg-error/10 transition-colors disabled:opacity-50"
        >
          <span className="material-symbols-outlined text-[18px]">{loggingOut ? "progress_activity" : "logout"}</span>
          {loggingOut ? "Saindo…" : "Sair da conta"}
        </button>
      </div>
    </div>
  );
}

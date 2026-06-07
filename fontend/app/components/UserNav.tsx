"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authClient, useSession } from "@/lib/auth-client";

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
  const ref = useRef<HTMLDivElement>(null);

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
    await authClient.signOut();
    router.push("/login");
    router.refresh();
  }

  const Avatar = (
    <div className={`${variant === "mobile" ? "h-10 w-10" : "h-8 w-8"} rounded-full bg-gradient-to-tr from-primary to-secondary p-[1px] flex-shrink-0`}>
      <div className="rounded-full h-full w-full bg-surface-dark flex items-center justify-center">
        <span className="text-xs font-bold text-white">{initials}</span>
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
        {open && <Menu name={name} email={email} role={role} onLogout={handleLogout} loggingOut={loggingOut} />}
      </div>
    );
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-gray-800 transition-colors text-left focus:outline-none focus:ring-2 focus:ring-primary/50"
      >
        {Avatar}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-white truncate">{name}</p>
          <p className="text-xs text-gray-500 truncate">{email || "—"}</p>
        </div>
        <span className="material-symbols-outlined text-gray-500 text-[18px]">unfold_more</span>
      </button>
      {open && <Menu name={name} email={email} role={role} onLogout={handleLogout} loggingOut={loggingOut} />}
    </div>
  );
}

function Menu({
  name,
  email,
  role,
  onLogout,
  loggingOut,
}: {
  name: string;
  email: string;
  role: string;
  onLogout: () => void;
  loggingOut: boolean;
}) {
  return (
    <div className="absolute bottom-full right-0 mb-2 w-60 rounded-xl border border-border-dark bg-surface-dark shadow-xl overflow-hidden z-50 animate-in">
      <div className="px-4 py-3 border-b border-border-dark/60">
        <p className="text-sm font-semibold text-white truncate">{name}</p>
        <p className="text-xs text-gray-500 truncate">{email}</p>
        <span className="mt-2 inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wide"
          style={{
            color: role === "admin" ? "var(--color-secondary)" : "var(--color-primary)",
            background: role === "admin" ? "rgba(139,92,246,0.12)" : "rgba(6,182,212,0.12)",
          }}>
          <span className="material-symbols-outlined text-[12px]">{role === "admin" ? "shield_person" : "person"}</span>
          {role}
        </span>
      </div>
      <div className="p-1">
        <Link href="/conta" className="flex items-center gap-3 px-3 py-2 text-sm text-gray-300 rounded-lg hover:bg-gray-800 hover:text-white transition-colors">
          <span className="material-symbols-outlined text-[18px] text-primary/70">manage_accounts</span>
          Minha conta
        </Link>
        <button
          onClick={onLogout}
          disabled={loggingOut}
          className="w-full flex items-center gap-3 px-3 py-2 text-sm text-red-400 rounded-lg hover:bg-red-500/10 transition-colors disabled:opacity-50"
        >
          <span className="material-symbols-outlined text-[18px]">{loggingOut ? "progress_activity" : "logout"}</span>
          {loggingOut ? "Saindo…" : "Sair da conta"}
        </button>
      </div>
    </div>
  );
}

"use client";

import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { authClient } from "@/lib/auth-client";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const redirect = params.get("redirect") || "/";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    const { error } = await authClient.signIn.email({ email, password });
    setLoading(false);
    if (error) {
      setError(error.message || "Não foi possível entrar. Verifique e-mail e senha.");
      return;
    }
    router.push(redirect);
    router.refresh();
  }

  return (
    <div className="min-h-screen w-full flex items-center justify-center px-4 bg-bg-dark relative overflow-hidden">
      {/* glows de fundo */}
      <div className="pointer-events-none absolute -top-40 -left-40 h-96 w-96 rounded-full bg-primary/10 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -right-40 h-96 w-96 rounded-full bg-secondary/10 blur-3xl" />

      <div className="relative w-full max-w-sm">
        {/* logo */}
        <div className="flex items-center justify-center gap-2 mb-8">
          <span className="material-symbols-outlined text-primary text-4xl">school</span>
          <span className="text-3xl font-bold tracking-tight text-white">
            stud<span className="text-primary">IA</span>
          </span>
        </div>

        <div className="rounded-2xl border border-border-dark bg-surface-dark p-7 shadow-xl">
          <h1 className="text-xl font-bold text-white">Entrar</h1>
          <p className="mt-1 text-sm text-gray-500">Acesse sua plataforma de estudos</p>

          <form onSubmit={handleSubmit} className="mt-6 space-y-4">
            <div>
              <label className="block text-[0.7rem] font-semibold uppercase tracking-wide text-gray-500 mb-1.5">
                E-mail
              </label>
              <div className="relative">
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-gray-600 text-[20px] pointer-events-none">mail</span>
                <input
                  type="email"
                  required
                  autoFocus
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="voce@email.com"
                  className="w-full rounded-lg border border-border-dark bg-bg-dark py-2.5 pl-10 pr-3 text-sm text-white placeholder:text-gray-600 outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors"
                />
              </div>
            </div>

            <div>
              <label className="block text-[0.7rem] font-semibold uppercase tracking-wide text-gray-500 mb-1.5">
                Senha
              </label>
              <div className="relative">
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-gray-600 text-[20px] pointer-events-none">lock</span>
                <input
                  type={showPw ? "text" : "password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••"
                  className="w-full rounded-lg border border-border-dark bg-bg-dark py-2.5 pl-10 pr-10 text-sm text-white placeholder:text-gray-600 outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowPw((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-gray-600 hover:text-gray-400"
                  tabIndex={-1}
                >
                  <span className="material-symbols-outlined text-[20px]">{showPw ? "visibility_off" : "visibility"}</span>
                </button>
              </div>
            </div>

            {error && (
              <div className="flex items-start gap-2 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-400">
                <span className="material-symbols-outlined text-[18px]">error</span>
                <span>{error}</span>
              </div>
            )}

            <button
              type="submit"
              disabled={loading}
              className="w-full flex items-center justify-center gap-2 rounded-lg bg-primary py-2.5 text-sm font-semibold text-white shadow-[0_8px_24px_rgba(6,182,212,0.30)] hover:bg-primary-600 disabled:opacity-50 transition-colors"
            >
              {loading && <span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>}
              {loading ? "Entrando…" : "Entrar"}
            </button>
          </form>
        </div>

        <p className="mt-6 text-center text-xs text-gray-600">
          Acesso restrito · contas criadas pelo administrador
        </p>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  );
}

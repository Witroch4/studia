"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { authClient } from "@/lib/auth-client";
import Logo from "@/app/components/Logo";

function EsqueciSenhaForm() {
  const [email, setEmail] = useState("");
  const [loading, setLoading] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    // redirectTo: página onde o usuário escolhe a nova senha (recebe ?token=).
    const { error } = await authClient.requestPasswordReset({
      email,
      redirectTo: `${window.location.origin}/redefinir-senha`,
    });
    setLoading(false);
    if (error) {
      setError("Não foi possível enviar agora. Tente novamente em instantes.");
      return;
    }
    // Sempre mostramos sucesso (não revela se o e-mail existe).
    setSent(true);
  }

  return (
    <div className="min-h-screen w-full flex items-center justify-center px-4 bg-page relative overflow-hidden">
      <div className="pointer-events-none absolute -top-40 -left-40 h-96 w-96 rounded-full bg-primary/10 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -right-40 h-96 w-96 rounded-full bg-secondary/10 blur-3xl" />

      <div className="relative w-full max-w-sm">
        <Link href="/" className="flex items-center justify-center mb-8">
          <Logo size={40} wordClassName="text-3xl" />
        </Link>

        <div className="rounded-2xl border border-border bg-surface p-7 shadow-xl">
          {sent ? (
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/15">
                <span className="material-symbols-outlined text-primary text-[30px]">mark_email_read</span>
              </div>
              <h1 className="text-xl font-bold text-fg-strong">Verifique seu e-mail</h1>
              <p className="mt-2 text-sm text-fg-faint">
                Se houver uma conta para <span className="font-medium text-fg-muted">{email}</span>,
                enviamos um link para você redefinir a senha.
              </p>
            </div>
          ) : (
            <>
              <h1 className="text-xl font-bold text-fg-strong">Esqueci minha senha</h1>
              <p className="mt-1 text-sm text-fg-faint">
                Informe seu e-mail e enviaremos um link para criar uma nova senha.
              </p>

              <form onSubmit={handleSubmit} className="mt-6 space-y-4">
                <div>
                  <label className="block text-[0.7rem] font-semibold uppercase tracking-wide text-fg-faint mb-1.5">
                    E-mail
                  </label>
                  <div className="relative">
                    <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-fg-faint text-[20px] pointer-events-none">mail</span>
                    <input
                      type="email"
                      required
                      autoFocus
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="voce@email.com"
                      className="w-full rounded-lg border border-border bg-page py-2.5 pl-10 pr-3 text-sm text-fg-strong placeholder:text-fg-faint outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors"
                    />
                  </div>
                </div>

                {error && (
                  <div className="flex items-start gap-2 rounded-lg border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">
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
                  {loading ? "Enviando…" : "Enviar link"}
                </button>
              </form>
            </>
          )}
        </div>

        <p className="mt-6 text-center text-xs text-fg-faint">
          Lembrou a senha?{" "}
          <Link href="/login" className="text-primary hover:underline font-medium">
            Entrar
          </Link>
        </p>
      </div>
    </div>
  );
}

export default function EsqueciSenhaPage() {
  return (
    <Suspense fallback={null}>
      <EsqueciSenhaForm />
    </Suspense>
  );
}

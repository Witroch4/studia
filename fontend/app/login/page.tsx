"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { authClient } from "@/lib/auth-client";
import Logo from "@/app/components/Logo";
import GoogleAuthButton from "@/app/components/GoogleAuthButton";

function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const redirect = params.get("redirect") || "/painel";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [needsVerify, setNeedsVerify] = useState(false);
  const [resendMsg, setResendMsg] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setNeedsVerify(false);
    setResendMsg(null);
    setLoading(true);
    const { error } = await authClient.signIn.email({ email, password });
    setLoading(false);
    if (error) {
      // 403 EMAIL_NOT_VERIFIED: conta existe mas falta confirmar o e-mail.
      if (error.status === 403 || error.code === "EMAIL_NOT_VERIFIED") {
        setNeedsVerify(true);
        setError("Confirme seu e-mail antes de entrar. Reenviamos o link, se precisar.");
        return;
      }
      setError(error.message || "Não foi possível entrar. Verifique e-mail e senha.");
      return;
    }
    router.push(redirect);
    router.refresh();
  }

  async function handleResend() {
    setResendMsg(null);
    if (!email) {
      setResendMsg("Digite seu e-mail acima primeiro.");
      return;
    }
    const { error } = await authClient.sendVerificationEmail({
      email,
      callbackURL: "/painel",
    });
    setResendMsg(
      error ? "Não foi possível reenviar agora. Tente em instantes." : "E-mail de confirmação reenviado!"
    );
  }

  return (
    <div className="min-h-screen w-full flex items-center justify-center px-4 bg-page relative overflow-hidden">
      {/* glows de fundo */}
      <div className="pointer-events-none absolute -top-40 -left-40 h-96 w-96 rounded-full bg-primary/10 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-40 -right-40 h-96 w-96 rounded-full bg-secondary/10 blur-3xl" />

      <div className="relative w-full max-w-sm">
        {/* logo */}
        <Link href="/" className="flex items-center justify-center mb-8">
          <Logo size={40} wordClassName="text-3xl" />
        </Link>

        <div className="rounded-2xl border border-border bg-surface p-7 shadow-xl">
          <h1 className="text-xl font-bold text-fg-strong">Entrar</h1>
          <p className="mt-1 text-sm text-fg-faint">Acesse sua plataforma de estudos</p>

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

            <div>
              <label className="block text-[0.7rem] font-semibold uppercase tracking-wide text-fg-faint mb-1.5">
                Senha
              </label>
              <div className="relative">
                <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-fg-faint text-[20px] pointer-events-none">lock</span>
                <input
                  type={showPw ? "text" : "password"}
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••"
                  className="w-full rounded-lg border border-border bg-page py-2.5 pl-10 pr-10 text-sm text-fg-strong placeholder:text-fg-faint outline-none focus:border-primary focus:ring-1 focus:ring-primary transition-colors"
                />
                <button
                  type="button"
                  onClick={() => setShowPw((v) => !v)}
                  className="absolute right-2 top-1/2 -translate-y-1/2 p-1 text-fg-faint hover:text-fg-muted"
                  tabIndex={-1}
                >
                  <span className="material-symbols-outlined text-[20px]">{showPw ? "visibility_off" : "visibility"}</span>
                </button>
              </div>
            </div>

            <div className="flex justify-end -mt-1">
              <Link href="/esqueci-senha" className="text-xs text-fg-faint hover:text-primary transition-colors">
                Esqueci minha senha
              </Link>
            </div>

            {error && (
              <div className="flex flex-col gap-2 rounded-lg border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">
                <div className="flex items-start gap-2">
                  <span className="material-symbols-outlined text-[18px]">error</span>
                  <span>{error}</span>
                </div>
                {needsVerify && (
                  <button
                    type="button"
                    onClick={handleResend}
                    className="self-start text-xs font-semibold text-primary hover:underline"
                  >
                    Reenviar e-mail de confirmação
                  </button>
                )}
              </div>
            )}

            {resendMsg && (
              <div className="rounded-lg border border-primary/30 bg-primary/10 px-3 py-2 text-sm text-primary">
                {resendMsg}
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

          <GoogleAuthButton callbackURL={redirect} />
        </div>

        <p className="mt-6 text-center text-xs text-fg-faint">
          Não tem conta?{" "}
          <Link href="/cadastro" className="text-primary hover:underline font-medium">
            Criar conta grátis
          </Link>
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

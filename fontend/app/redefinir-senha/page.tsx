"use client";

import { Suspense, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { authClient } from "@/lib/auth-client";
import Logo from "@/app/components/Logo";

function RedefinirSenhaForm() {
  const router = useRouter();
  const params = useSearchParams();
  const token = params.get("token");
  const linkError = params.get("error"); // ex.: INVALID_TOKEN

  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPw, setShowPw] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [done, setDone] = useState(false);

  const tokenInvalid = !token || !!linkError;

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (password.length < 6) {
      setError("A senha precisa de ao menos 6 caracteres.");
      return;
    }
    if (password !== confirm) {
      setError("As senhas não coincidem.");
      return;
    }
    setLoading(true);
    const { error } = await authClient.resetPassword({ newPassword: password, token: token! });
    setLoading(false);
    if (error) {
      setError(error.message || "Link inválido ou expirado. Peça um novo.");
      return;
    }
    setDone(true);
    setTimeout(() => router.push("/login"), 1800);
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
          {done ? (
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-primary/15">
                <span className="material-symbols-outlined text-primary text-[30px]">check_circle</span>
              </div>
              <h1 className="text-xl font-bold text-fg-strong">Senha redefinida!</h1>
              <p className="mt-2 text-sm text-fg-faint">Levando você para o login…</p>
            </div>
          ) : tokenInvalid ? (
            <div className="text-center">
              <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-error/15">
                <span className="material-symbols-outlined text-error text-[30px]">link_off</span>
              </div>
              <h1 className="text-xl font-bold text-fg-strong">Link inválido ou expirado</h1>
              <p className="mt-2 text-sm text-fg-faint">
                Este link de redefinição não é mais válido. Solicite um novo.
              </p>
              <Link
                href="/esqueci-senha"
                className="mt-5 inline-block rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-white hover:bg-primary-600 transition-colors"
              >
                Pedir novo link
              </Link>
            </div>
          ) : (
            <>
              <h1 className="text-xl font-bold text-fg-strong">Nova senha</h1>
              <p className="mt-1 text-sm text-fg-faint">Escolha uma senha para sua conta.</p>

              <form onSubmit={handleSubmit} className="mt-6 space-y-4">
                <div>
                  <label className="block text-[0.7rem] font-semibold uppercase tracking-wide text-fg-faint mb-1.5">
                    Nova senha
                  </label>
                  <div className="relative">
                    <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-fg-faint text-[20px] pointer-events-none">lock</span>
                    <input
                      type={showPw ? "text" : "password"}
                      required
                      autoFocus
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                      placeholder="mínimo 6 caracteres"
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

                <div>
                  <label className="block text-[0.7rem] font-semibold uppercase tracking-wide text-fg-faint mb-1.5">
                    Confirmar senha
                  </label>
                  <div className="relative">
                    <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-fg-faint text-[20px] pointer-events-none">lock</span>
                    <input
                      type={showPw ? "text" : "password"}
                      required
                      value={confirm}
                      onChange={(e) => setConfirm(e.target.value)}
                      placeholder="repita a senha"
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
                  {loading ? "Salvando…" : "Redefinir senha"}
                </button>
              </form>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export default function RedefinirSenhaPage() {
  return (
    <Suspense fallback={null}>
      <RedefinirSenhaForm />
    </Suspense>
  );
}

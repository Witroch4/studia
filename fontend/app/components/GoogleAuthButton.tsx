"use client";

import { useState } from "react";
import { authClient } from "@/lib/auth-client";

/**
 * Botão "Continuar com Google" (Better Auth social sign-in).
 *
 * Visibilidade gateada por NEXT_PUBLIC_GOOGLE_AUTH — inlinado no bundle em
 * build-time (build.sh deriva "1" quando há GOOGLE_CLIENT_ID no .env). Enquanto
 * as chaves do Google não existem, o flag fica vazio e o botão não renderiza,
 * então login/cadastro continuam funcionando só com e-mail/senha.
 */
export default function GoogleAuthButton({
  callbackURL = "/painel",
  label = "Continuar com Google",
}: {
  callbackURL?: string;
  label?: string;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (process.env.NEXT_PUBLIC_GOOGLE_AUTH !== "1") return null;

  async function handleGoogle() {
    setError(null);
    setLoading(true);
    // Redireciona ao Google; em caso de erro volta sem navegar.
    const { error } = await authClient.signIn.social({ provider: "google", callbackURL });
    if (error) {
      setLoading(false);
      setError(error.message || "Não foi possível entrar com o Google. Tente novamente.");
    }
  }

  return (
    <div className="mt-5">
      <div className="flex items-center gap-3">
        <span className="h-px flex-1 bg-border" />
        <span className="text-[0.7rem] uppercase tracking-wide text-fg-faint">ou</span>
        <span className="h-px flex-1 bg-border" />
      </div>

      <button
        type="button"
        onClick={handleGoogle}
        disabled={loading}
        className="mt-4 w-full flex items-center justify-center gap-3 rounded-lg border border-border bg-page py-2.5 text-sm font-semibold text-fg-strong hover:bg-surface disabled:opacity-50 transition-colors"
      >
        {loading ? (
          <span className="material-symbols-outlined text-[18px] animate-spin">progress_activity</span>
        ) : (
          <GoogleIcon />
        )}
        <span>{loading ? "Conectando…" : label}</span>
      </button>

      {error && (
        <div className="mt-3 flex items-start gap-2 rounded-lg border border-error/30 bg-error/10 px-3 py-2 text-sm text-error">
          <span className="material-symbols-outlined text-[18px]">error</span>
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}

function GoogleIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.7-1.57 2.68-3.88 2.68-6.62z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72A5.4 5.4 0 0 1 3.68 9c0-.6.1-1.18.29-1.72V4.95H.96A9 9 0 0 0 0 9c0 1.45.35 2.82.96 4.05l3.01-2.33z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58z"
      />
    </svg>
  );
}

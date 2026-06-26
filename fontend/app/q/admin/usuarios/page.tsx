"use client";

import dynamic from "next/dynamic";

// Carregado só no cliente: usa useSession (better-auth/react), que não pode
// rodar no prerender/SSR enquanto o better-auth está externalizado.
const AdminUsuariosClient = dynamic(() => import("./AdminUsuariosClient"), {
  ssr: false,
  loading: () => <div className="p-8 text-sm text-fg-faint">Carregando…</div>,
});

export default function AdminUsuariosPage() {
  return <AdminUsuariosClient />;
}

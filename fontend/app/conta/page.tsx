"use client";

import dynamic from "next/dynamic";

// Carregado só no cliente: o corpo usa useSession (better-auth/react), que não
// pode rodar no prerender/SSR enquanto o better-auth está externalizado.
const ContaClient = dynamic(() => import("./ContaClient"), {
  ssr: false,
  loading: () => <div className="px-6 py-8 text-sm text-gray-500">Carregando…</div>,
});

export default function ContaPage() {
  return <ContaClient />;
}

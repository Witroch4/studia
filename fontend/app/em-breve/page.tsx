"use client";

import { useSearchParams } from "next/navigation";
import Link from "next/link";
import { Suspense } from "react";

const ICONS: Record<string, string> = {
  Planejamento: "calendar_month",
  Revisões: "autorenew",
  Histórico: "history",
  Estatísticas: "bar_chart",
  Simulados: "quiz",
};

function ComingSoonContent() {
  const params = useSearchParams();
  const feature = params.get("f") ?? "Esta funcionalidade";
  const icon = ICONS[feature] ?? "rocket_launch";

  return (
    <div className="min-h-screen flex flex-col items-center justify-center text-center px-6">
      <div className="mb-6 flex items-center justify-center w-24 h-24 rounded-full bg-primary/10 ring-1 ring-primary/30">
        <span className="material-symbols-outlined text-[48px] text-primary">{icon}</span>
      </div>

      <h1 className="text-3xl font-bold text-white mb-2">{feature}</h1>
      <p className="text-gray-400 text-base max-w-sm mb-8">
        Estamos construindo isso. Em breve estará disponível para você.
      </p>

      <div className="flex items-center gap-2 mb-10">
        {[0, 1, 2].map((i) => (
          <span
            key={i}
            className="block w-2 h-2 rounded-full bg-primary/40 animate-pulse"
            style={{ animationDelay: `${i * 200}ms` }}
          />
        ))}
      </div>

      <Link
        href="/painel"
        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-primary/10 text-primary text-sm font-medium hover:bg-primary/20 transition-colors"
      >
        <span className="material-symbols-outlined text-[18px]">arrow_back</span>
        Voltar ao início
      </Link>
    </div>
  );
}

export default function EmBreve() {
  return (
    <Suspense>
      <ComingSoonContent />
    </Suspense>
  );
}

"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import dynamic from "next/dynamic";
import { authClient } from "@/lib/auth-client";
import Logo from "./Logo";

// Carregado só no cliente: usa useSession (better-auth/react), que não pode
// rodar no prerender/SSR enquanto o better-auth está externalizado.
const UserNav = dynamic(() => import("./UserNav"), {
  ssr: false,
  loading: () => <div className="h-12" />,
});

type NavItem = { href: string; label: string; icon: string; adminOnly?: boolean };

const navItems: NavItem[] = [
  { href: "/painel", label: "Início", icon: "home" },
  { href: "/flashcards", label: "Flashcards", icon: "style" },
  { href: "/disciplinas", label: "Disciplinas", icon: "library_books" },
  { href: "/q/filtrar", label: "Questões", icon: "fact_check" },
  { href: "/q/cadernos", label: "Minhas Pastas", icon: "folder" },
  { href: "/q/guias", label: "Guias", icon: "menu_book" },
  // Coleta TC: área de administração — só admin vê e usa (backend também exige admin).
  { href: "/q/coletar", label: "Coletar TC", icon: "cloud_download", adminOnly: true },
  { href: "/concorrencia", label: "Concorrência", icon: "leaderboard" },
  { href: "/jobs", label: "Jobs IA", icon: "monitoring" },
  { href: "#", label: "Planejamento", icon: "calendar_month" },
  { href: "#", label: "Revisões", icon: "autorenew" },
  { href: "#", label: "Histórico", icon: "history" },
  { href: "#", label: "Estatísticas", icon: "bar_chart" },
  { href: "#", label: "Simulados", icon: "quiz" },
];

export default function Sidebar() {
  const pathname = usePathname();
  // better-auth é externalizado → o hook useSession quebra no prerender/SSR.
  // Lemos a sessão só no cliente (useEffect), sem layout shift do sidebar.
  const [isAdmin, setIsAdmin] = useState(false);
  useEffect(() => {
    authClient
      .getSession()
      .then((res) => {
        const role = (res?.data?.user as { role?: string } | undefined)?.role;
        setIsAdmin(role === "admin");
      })
      .catch(() => {});
  }, []);
  const itensVisiveis = navItems.filter((item) => !item.adminOnly || isAdmin);

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex flex-col w-64 h-screen sticky top-0 bg-surface-dark border-r border-border-dark flex-shrink-0 overflow-y-auto z-50">
        <Link href="/painel" className="p-6 flex items-center border-b border-border-dark/50">
          <Logo size={30} wordClassName="text-2xl" />
        </Link>

        <nav className="flex-1 p-4 space-y-1">
          {itensVisiveis.map((item) => {
            const isActive = item.href === "/painel" ? pathname === "/painel" : pathname.startsWith(item.href) && item.href !== "#";
            return (
              <Link
                key={item.label}
                href={item.href}
                className={`flex items-center gap-3 px-4 py-3 text-sm font-medium rounded-lg transition-colors group ${
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-gray-400 hover:text-white hover:bg-gray-800"
                }`}
              >
                <span
                  className={`material-symbols-outlined text-[20px] ${
                    isActive ? "" : "text-primary/70 group-hover:text-primary"
                  }`}
                >
                  {item.icon}
                </span>
                {item.label}
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-border-dark/50">
          <UserNav variant="desktop" />
        </div>
      </aside>

      {/* Mobile top nav */}
      <nav className="sticky top-0 z-40 bg-surface-dark border-b border-border-dark px-4 py-3 shadow-sm md:hidden">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button className="p-2 rounded-md hover:bg-gray-800 text-gray-300">
              <span className="material-symbols-outlined">menu</span>
            </button>
            <Link href="/painel" className="flex items-center">
              <Logo size={28} wordClassName="text-2xl" />
            </Link>
          </div>
          <div className="flex items-center gap-4">
            <button className="p-2 rounded-full hover:bg-gray-800 text-gray-300 relative">
              <span className="material-symbols-outlined">notifications</span>
              <span className="absolute top-2 right-2 h-2 w-2 rounded-full bg-secondary animate-pulse" />
            </button>
            <UserNav variant="mobile" />
          </div>
        </div>
      </nav>
    </>
  );
}

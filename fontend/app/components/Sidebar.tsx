"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import dynamic from "next/dynamic";
import { authClient } from "@/lib/auth-client";
import { ensureHandoff } from "@/lib/api";
import Logo from "./Logo";
import { AnimatedThemeToggle } from "./AnimatedThemeToggle";

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
  // Pastas de usuários: monta guias a partir dos cadernos de qualquer usuário — admin.
  { href: "/q/admin/pastas", label: "Pastas de usuários", icon: "folder_shared", adminOnly: true },
  // Coleta TC: área de administração — só admin vê e usa (backend também exige admin).
  { href: "/q/coletar", label: "Coletar TC", icon: "cloud_download", adminOnly: true },
  { href: "/concorrencia", label: "Concorrência", icon: "leaderboard" },
  // Jobs IA: processamento de PDFs (Gemini Batch) — área de administração.
  { href: "/jobs", label: "Jobs IA", icon: "monitoring", adminOnly: true },
  // Vouchers PRO: geração e controle de resgates — área de administração.
  { href: "/admin/vouchers", label: "Vouchers", icon: "redeem", adminOnly: true },
  // Assinaturas: gestão Stripe (overview, conceder/cancelar) — área de administração.
  { href: "/admin/assinaturas", label: "Assinaturas", icon: "paid", adminOnly: true },
  { href: "/planejamento", label: "Planejamento", icon: "calendar_month" },
  { href: "/em-breve?f=Revisões", label: "Revisões", icon: "autorenew" },
  { href: "/em-breve?f=Histórico", label: "Histórico", icon: "history" },
  { href: "/em-breve?f=Estatísticas", label: "Estatísticas", icon: "bar_chart" },
  { href: "/em-breve?f=Simulados", label: "Simulados", icon: "quiz" },
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
        // Handoff proativo: minta o JWT/CSRF antes da primeira ação do usuário.
        if (res?.data?.session) ensureHandoff().catch(() => {});
      })
      .catch(() => {});
  }, []);
  const itensVisiveis = navItems.filter((item) => !item.adminOnly || isAdmin);

  // Recolher/expandir a sidebar de forma IMPERATIVA: só alterna a classe no
  // <html> e persiste no localStorage. Sem useState → o markup React é idêntico
  // server/client, então não há mismatch de hidratação (o estado vive no CSS).
  const toggleSidebar = () => {
    const el = document.documentElement;
    const collapsed = el.classList.toggle("sidebar-collapsed");
    try {
      localStorage.setItem("studia-sidebar", collapsed ? "collapsed" : "expanded");
    } catch {}
  };

  return (
    <>
      {/* Desktop sidebar */}
      <aside
        data-sidebar
        className="hidden md:flex flex-col w-64 h-screen sticky top-0 bg-surface-dark border-r border-border-dark flex-shrink-0 overflow-y-auto z-50"
      >
        <div className="flex items-center border-b border-border-dark/50 sidebar-row">
          <Link href="/painel" className="sidebar-label flex-1 min-w-0 p-6 flex items-center">
            <Logo size={30} wordClassName="text-2xl" />
          </Link>
          {/* Chevron SEMPRE visível: recolhe quando expandida, reexpande quando
              colapsada (o ícone rotaciona 180° via CSS no estado colapsado). */}
          <button
            type="button"
            onClick={toggleSidebar}
            aria-label="Recolher ou expandir menu"
            title="Recolher / expandir menu"
            className="mx-2 p-2 rounded-lg text-fg-muted hover:text-fg-strong hover:bg-fg-strong/6"
          >
            <span className="material-symbols-outlined sidebar-collapse-icon text-[20px]">chevron_left</span>
          </button>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {itensVisiveis.map((item) => {
            const isActive = item.href === "/painel" ? pathname === "/painel" : !item.href.startsWith("/em-breve") && pathname.startsWith(item.href);
            return (
              <Link
                key={item.label}
                href={item.href}
                title={item.label}
                className={`sidebar-link flex items-center gap-3 px-4 py-3 text-sm font-medium rounded-lg transition-colors group ${
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-fg-muted hover:text-fg-strong hover:bg-fg-strong/6"
                }`}
              >
                <span
                  className={`material-symbols-outlined text-[20px] shrink-0 ${
                    isActive ? "" : "text-primary/70 group-hover:text-primary"
                  }`}
                >
                  {item.icon}
                </span>
                <span className="sidebar-label">{item.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="p-4 border-t border-border-dark/50 space-y-3">
          {/* Botão recolher — visível só quando expandida (some no modo ícone;
              para reexpandir, use o chevron do topo, que rotaciona). */}
          <button
            type="button"
            onClick={toggleSidebar}
            className="sidebar-label w-full flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-fg-muted hover:text-fg-strong hover:bg-fg-strong/6"
          >
            <span className="material-symbols-outlined sidebar-collapse-icon text-[20px]">chevron_left</span>
            <span>Recolher menu</span>
          </button>
          <div className="flex items-center justify-between px-1 sidebar-row">
            <span className="text-xs font-medium text-fg-faint sidebar-label">Tema</span>
            <AnimatedThemeToggle />
          </div>
          <UserNav variant="desktop" />
        </div>
      </aside>

      {/* Mobile top nav */}
      <nav className="sticky top-0 z-40 bg-surface-dark border-b border-border-dark px-4 py-3 shadow-sm md:hidden">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <button className="p-2 rounded-md hover:bg-fg-strong/6 text-fg-muted">
              <span className="material-symbols-outlined">menu</span>
            </button>
            <Link href="/painel" className="flex items-center">
              <Logo size={28} wordClassName="text-2xl" />
            </Link>
          </div>
          <div className="flex items-center gap-4">
            <AnimatedThemeToggle />
            <button className="p-2 rounded-full hover:bg-fg-strong/6 text-fg-muted relative">
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

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import dynamic from "next/dynamic";

// Carregado só no cliente: usa useSession (better-auth/react), que não pode
// rodar no prerender/SSR enquanto o better-auth está externalizado.
const UserNav = dynamic(() => import("./UserNav"), {
  ssr: false,
  loading: () => <div className="h-12" />,
});

const navItems = [
  { href: "/", label: "Home", icon: "home" },
  { href: "/flashcards", label: "Flashcards", icon: "style" },
  { href: "/disciplinas", label: "Disciplinas", icon: "library_books" },
  { href: "/q/filtrar", label: "Questões", icon: "fact_check" },
  { href: "/q/cadernos", label: "Minhas Pastas", icon: "folder" },
  { href: "/q/guias", label: "Guias", icon: "menu_book" },
  { href: "/q/coletar", label: "Coletar TC", icon: "cloud_download" },
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

  return (
    <>
      {/* Desktop sidebar */}
      <aside className="hidden md:flex flex-col w-64 h-screen sticky top-0 bg-surface-dark border-r border-border-dark flex-shrink-0 overflow-y-auto z-50">
        <div className="p-6 flex items-center gap-3 border-b border-border-dark/50">
          <span className="material-symbols-outlined text-primary text-3xl">school</span>
          <span className="text-2xl font-bold tracking-tight text-white">
            stud<span className="text-primary">IA</span>
          </span>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          {navItems.map((item) => {
            const isActive = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href) && item.href !== "#";
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
            <div className="flex items-center gap-2">
              <span className="material-symbols-outlined text-primary text-3xl">school</span>
              <span className="text-2xl font-bold tracking-tight text-white">
                stud<span className="text-primary">IA</span>
              </span>
            </div>
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

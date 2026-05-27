"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  { href: "/", label: "Home", icon: "home" },
  { href: "/flashcards", label: "Flashcards", icon: "style" },
  { href: "/disciplinas", label: "Disciplinas", icon: "library_books" },
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
          <div className="flex items-center gap-3 px-2 py-2">
            <div className="h-8 w-8 rounded-full bg-gradient-to-tr from-primary to-secondary p-[1px]">
              <div className="rounded-full h-full w-full bg-surface-dark flex items-center justify-center">
                <span className="text-xs font-bold text-white">EJ</span>
              </div>
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-white truncate">Engenheiro Jr.</p>
              <p className="text-xs text-gray-500 truncate cursor-pointer hover:text-gray-400">Sair da conta</p>
            </div>
          </div>
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
            <div className="h-10 w-10 rounded-full bg-gradient-to-tr from-primary to-secondary p-[2px]">
              <div className="rounded-full h-full w-full bg-surface-dark flex items-center justify-center">
                <span className="text-xs font-bold text-white">EJ</span>
              </div>
            </div>
          </div>
        </div>
      </nav>
    </>
  );
}

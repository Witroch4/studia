"use client";

import { usePathname } from "next/navigation";
import Sidebar from "./Sidebar";

/**
 * Decide o "chrome" do app: rotas de auth (ex.: /login) ficam fullscreen sem
 * sidebar; todo o resto ganha a sidebar + área de conteúdo.
 */
const BARE_ROUTES = ["/", "/login", "/cadastro"];

export default function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const isBare = BARE_ROUTES.some((r) => pathname === r || pathname.startsWith(r + "/"));

  if (isBare) {
    return <div className="flex-1 min-w-0 flex flex-col min-h-screen w-full">{children}</div>;
  }

  return (
    <>
      <Sidebar />
      <div className="flex-1 min-w-0 flex flex-col">{children}</div>
    </>
  );
}

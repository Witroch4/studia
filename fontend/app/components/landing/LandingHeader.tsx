"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import Logo from "../Logo";

const LINKS = [
  { href: "#recursos", label: "Recursos" },
  { href: "#como-funciona", label: "Como funciona" },
  { href: "#planos", label: "Planos" },
  { href: "#faq", label: "FAQ" },
];

export default function LandingHeader() {
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  return (
    <header
      className={`fixed inset-x-0 top-0 z-50 transition-colors duration-300 ${
        scrolled ? "border-b border-white/10 bg-[#0a0a0c]/80 backdrop-blur-xl" : "border-b border-transparent"
      }`}
    >
      <div className="mx-auto flex max-w-6xl items-center justify-between px-5 py-3.5">
        <Link href="/" aria-label="studIA — início" className="flex items-center">
          <Logo size={30} wordClassName="text-xl" />
        </Link>

        <nav className="hidden items-center gap-8 md:flex">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="lp-mono text-xs uppercase tracking-wider text-gray-400 transition-colors hover:text-white"
            >
              {l.label}
            </a>
          ))}
        </nav>

        <div className="hidden items-center gap-3 md:flex">
          <Link
            href="/login"
            className="lp-mono text-xs uppercase tracking-wider text-gray-300 transition-colors hover:text-white"
          >
            Entrar
          </Link>
          <Link
            href="/cadastro"
            className="group inline-flex items-center gap-1.5 rounded-full bg-primary px-4 py-2 text-sm font-semibold text-white shadow-[0_8px_24px_-6px_rgba(6,182,212,0.6)] transition-all hover:bg-primary-600"
          >
            Começar grátis
            <span className="material-symbols-outlined text-[18px] transition-transform group-hover:translate-x-0.5">
              arrow_forward
            </span>
          </Link>
        </div>

        {/* mobile toggle */}
        <button
          type="button"
          aria-label={open ? "Fechar menu" : "Abrir menu"}
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          className="inline-flex h-10 w-10 items-center justify-center rounded-lg text-gray-200 hover:bg-white/5 md:hidden"
        >
          <span className="material-symbols-outlined">{open ? "close" : "menu"}</span>
        </button>
      </div>

      {/* mobile sheet */}
      {open && (
        <div className="border-t border-white/10 bg-[#0a0a0c]/95 backdrop-blur-xl md:hidden">
          <nav className="mx-auto flex max-w-6xl flex-col gap-1 px-5 py-4">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="rounded-lg px-3 py-3 text-sm text-gray-300 hover:bg-white/5 hover:text-white"
              >
                {l.label}
              </a>
            ))}
            <div className="mt-2 flex flex-col gap-2">
              <Link
                href="/login"
                className="rounded-lg border border-white/10 px-3 py-3 text-center text-sm font-medium text-gray-200 hover:bg-white/5"
              >
                Entrar
              </Link>
              <Link
                href="/cadastro"
                className="rounded-lg bg-primary px-3 py-3 text-center text-sm font-semibold text-white"
              >
                Começar grátis
              </Link>
            </div>
          </nav>
        </div>
      )}
    </header>
  );
}

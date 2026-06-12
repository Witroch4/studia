/**
 * Configuração canônica do site — fonte única para SEO, metadata, sitemap,
 * robots, manifest e dados estruturados (JSON-LD).
 *
 * URL de produção vem de NEXT_PUBLIC_SITE_URL; cai para o domínio conhecido.
 */
const url = (process.env.NEXT_PUBLIC_SITE_URL || "https://studia.witdev.com.br").replace(/\/$/, "");

export const siteConfig = {
  name: "studIA",
  url,
  /** Título "default" da home / fallback. */
  title: "studIA — Estude para concursos com Inteligência Artificial",
  /** Descrição usada em meta description e OpenGraph. */
  description:
    "Plataforma de estudos com IA para concursos públicos: banco de questões das maiores bancas, flashcards com repetição espaçada, resumos e flashcards gerados de PDFs por IA, e um tutor que explica cada aula. Comece grátis.",
  locale: "pt_BR",
  author: "WitDev",
  themeColor: "#06b6d4",
  background: "#0a0a0c",
  keywords: [
    "estudo para concursos",
    "questões de concurso",
    "flashcards",
    "repetição espaçada",
    "inteligência artificial para estudos",
    "banco de questões",
    "Cebraspe",
    "FGV",
    "FCC",
    "VUNESP",
    "resumo de PDF com IA",
    "plataforma de estudos",
    "studIA",
  ],
} as const;

/** Rotas públicas indexáveis (alimenta o sitemap). */
export const publicRoutes = ["/", "/login", "/cadastro", "/assinar"] as const;

export type SiteConfig = typeof siteConfig;

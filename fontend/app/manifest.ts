import type { MetadataRoute } from "next";
import { siteConfig } from "@/lib/site";

/**
 * Web App Manifest (PWA) — instalável, tema dark + ciano da marca.
 */
export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "studIA — Estudo inteligente para concursos",
    short_name: "studIA",
    description: siteConfig.description,
    start_url: "/painel",
    scope: "/",
    display: "standalone",
    background_color: siteConfig.background,
    theme_color: siteConfig.themeColor,
    lang: "pt-BR",
    categories: ["education", "productivity"],
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any" },
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "maskable" },
    ],
  };
}

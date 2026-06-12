import type { MetadataRoute } from "next";
import { siteConfig, publicRoutes } from "@/lib/site";

/**
 * /sitemap.xml — só rotas públicas indexáveis (o app fica atrás de login).
 */
export default function sitemap(): MetadataRoute.Sitemap {
  const lastModified = new Date();
  return publicRoutes.map((route) => ({
    url: `${siteConfig.url}${route === "/" ? "" : route}`,
    lastModified,
    changeFrequency: route === "/" ? "weekly" : "monthly",
    priority: route === "/" ? 1 : 0.6,
  }));
}

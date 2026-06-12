import type { MetadataRoute } from "next";
import { siteConfig } from "@/lib/site";

/**
 * /robots.txt — indexa o público, bloqueia área logada e APIs.
 */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: ["/api/", "/painel", "/conta", "/jobs", "/q/coletar"],
      },
    ],
    sitemap: `${siteConfig.url}/sitemap.xml`,
    host: siteConfig.url,
  };
}

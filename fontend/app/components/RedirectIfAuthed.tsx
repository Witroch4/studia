"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { authClient } from "@/lib/auth-client";

/**
 * Ilha de cliente para a landing pública: se já houver sessão, manda o usuário
 * direto pro painel. Como o better-auth é externalizado, a sessão só é lida no
 * cliente — o HTML da landing continua íntegro para crawlers/SEO.
 */
export default function RedirectIfAuthed({ to = "/painel" }: { to?: string }) {
  const router = useRouter();
  useEffect(() => {
    let alive = true;
    authClient
      .getSession()
      .then((res) => {
        if (alive && res?.data?.user) router.replace(to);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [router, to]);
  return null;
}

import { NextRequest, NextResponse } from "next/server";
import { getSessionCookie } from "better-auth/cookies";

/**
 * Proteção otimista de rotas (estilo proxy do platform-core).
 * Só checa a PRESENÇA do cookie de sessão — NÃO bate no banco. A validação
 * real acontece no servidor/quando o cookieCache expira.
 *
 * Público: a landing ("/"), as páginas de auth e os arquivos de SEO. Todo o
 * resto (o app em /painel, /q, /disciplinas, …) exige sessão.
 */
const AUTH_PREFIXES = ["/login", "/cadastro"];

// Públicas, mas SEM o redirect "logado → painel": quem chega aqui pode ter um
// cookie de sessão antigo e ainda precisar concluir o fluxo (ex.: clicou no
// link de redefinição de senha que recebeu por e-mail).
const RESET_PREFIXES = ["/esqueci-senha", "/redefinir-senha"];

// Perfil público /u/[apelido]: acessível sem login e sem redirect p/ painel
// (usuário logado também precisa conseguir ver o perfil de outra pessoa).
const PUBLIC_PREFIXES = ["/u"];

// Rotas de metadata que o matcher não exclui por extensão (precisam ser
// alcançáveis por crawlers sem login). /icon.svg já passa pelo matcher (.svg).
const SEO_FILES = new Set([
  "/robots.txt",
  "/sitemap.xml",
  "/manifest.webmanifest",
  "/opengraph-image",
  "/twitter-image",
  "/apple-icon",
]);

export default function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = getSessionCookie(request);

  const isLanding = pathname === "/";
  const isAuthPage = AUTH_PREFIXES.some((r) => pathname === r || pathname.startsWith(r + "/"));
  const isResetPage = RESET_PREFIXES.some((r) => pathname === r || pathname.startsWith(r + "/"));
  const isPublicPage = PUBLIC_PREFIXES.some((r) => pathname === r || pathname.startsWith(r + "/"));
  const isPublic = isLanding || isAuthPage || isResetPage || isPublicPage || SEO_FILES.has(pathname);

  // Logado na landing ou nas páginas de auth → vai pro painel (sem flash).
  // Crawler/visitante sem cookie continua vendo a landing normalmente.
  if (hasSession && (isLanding || isAuthPage)) {
    return NextResponse.redirect(new URL("/painel", request.url));
  }

  // Não logado tentando rota privada → /login (com redirect de volta).
  if (!isPublic && !hasSession) {
    const url = new URL("/login", request.url);
    url.searchParams.set("redirect", pathname);
    return NextResponse.redirect(url);
  }

  return NextResponse.next();
}

export const config = {
  // Protege tudo, menos os internos do Next, a API de auth e assets estáticos.
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};

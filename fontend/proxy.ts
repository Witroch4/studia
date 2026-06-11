import { NextRequest, NextResponse } from "next/server";
import { getSessionCookie } from "better-auth/cookies";

/**
 * Proteção otimista de rotas (estilo proxy do platform-core).
 * Só checa a PRESENÇA do cookie de sessão — NÃO bate no banco. A validação
 * real acontece no servidor/quando o cookieCache expira.
 */
const PUBLIC_ROUTES = ["/login", "/cadastro"];

export default function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  const hasSession = getSessionCookie(request);
  const isPublic = PUBLIC_ROUTES.some((r) => pathname === r || pathname.startsWith(r + "/"));

  // Não logado tentando rota privada → /login (com redirect de volta)
  if (!isPublic && !hasSession) {
    const url = new URL("/login", request.url);
    if (pathname !== "/") url.searchParams.set("redirect", pathname);
    return NextResponse.redirect(url);
  }

  // Já logado tentando /login → manda pra home
  if (isPublic && hasSession) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  return NextResponse.next();
}

export const config = {
  // Protege tudo, menos os internos do Next, a API de auth e assets estáticos.
  matcher: ["/((?!api/auth|_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)"],
};

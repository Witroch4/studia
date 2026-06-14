# Migração studIA → padrão · Plano 03: Auth cookie-JWT (handoff + CSRF)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Parar de bater no banco a cada request autenticado. O FastAPI passa a validar a sessão por **JWT em cookie HttpOnly** (decode `jose`, zero I/O), emitido por um **handoff explícito** que lê a sessão Better Auth uma única vez. Mutações exigem **CSRF** (double-submit). Padrão fiel ao platform-core (§7 da spec).

**Architecture:**
- **Handoff** `POST /api/auth/handoff`: lê o cookie `better-auth.session_token`, valida contra a tabela `session` **uma vez** (lógica atual do `auth.py`), e seta dois cookies: `studia_session` (HttpOnly, JWT assinado com claims `sub/email/name/role/exp`) e `studia_csrf` (legível pelo JS, valor aleatório).
- **Per-request** (`get_current_user_opt`): decodifica `studia_session` (jose), **zero DB**. Sem JWT válido → `None` (→ 401 nos endpoints protegidos).
- **CSRF**: middleware exige `X-CSRF-Token == cookie studia_csrf` em métodos mutadores (POST/PUT/PATCH/DELETE), exceto o próprio `/api/auth/handoff` e `/api/auth/logout`.
- **Frontend**: `lib/api.ts` ganha (1) header `X-CSRF-Token` automático em mutações e (2) interceptor que, ao receber 401, chama o handoff **uma vez** (guard anti-loop) e refaz a request. Todos os `fetch()` crus migram para `apiFetch`.
- **Sem lockout:** usuários logados hoje (têm cookie Better Auth, não têm JWT) recebem 401 na 1ª request → o interceptor faz handoff (mint do JWT) → retry → segue. Deploy de front+back é atômico (um `build.sh`/stack deploy); a janela de rolling-update pode dar um blip para quem está com o front antigo em cache (resolve com refresh).

**Tech Stack:** FastAPI, python-jose, Next.js (fetch), pytest.

**Pré-requisito:** Planos 01 (Alembic + testes Postgres) mergeados. Suíte verde via `./dev.sh test -q`. Rodar a suíte após cada task de backend.

**Env nova:** `STUDIA_JWT_SECRET` (segredo de assinatura do JWT). Fallback de dev no código; em prod vem de `/opt/studia/.env`. **Adicionar a chave ao `.env` de prod antes do deploy** (passo no fim).

---

### Task 1: Backend — utilitários de segurança (JWT + CSRF + cookies)

**Files:**
- Modify: `backend/requirements.txt` (add `python-jose[cryptography]`)
- Create: `backend/security.py`

- [ ] **Step 1: Dependência.** Em `backend/requirements.txt`, abaixo de `alembic>=1.13,<2`, adicione:
```
python-jose[cryptography]>=3.3,<4
```
Instale + verifique:
```bash
./dev.sh shell backend -c "pip install -r requirements.txt && python -c 'import jose; print(jose.__name__, \"ok\")'"
```
Expected: `jose ok`.

- [ ] **Step 2: Criar `backend/security.py`**:
```python
"""Tokens de sessão do studIA: JWT em cookie HttpOnly + CSRF double-submit.

O FastAPI valida a sessão decodificando o JWT (zero I/O no banco). O JWT é
emitido no handoff (que lê a sessão Better Auth uma vez). CSRF é double-submit:
o cookie `studia_csrf` (legível) precisa casar com o header X-CSRF-Token.
"""

from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

SESSION_COOKIE = "studia_session"
CSRF_COOKIE = "studia_csrf"
_ALG = "HS256"
_TTL_MIN = int(os.getenv("STUDIA_JWT_TTL_MIN", "30"))
_SECRET = os.getenv(
    "STUDIA_JWT_SECRET",
    "studia-dev-jwt-secret-change-in-prod-0001",  # fallback só de dev
)
# Cookies seguros (HTTPS) em produção; em dev (HTTP) precisam de Secure=False.
_SECURE = os.getenv("STUDIA_COOKIE_SECURE", "true").lower() != "false"


def mint_session_jwt(*, user_id: str, email: str, name: str, role: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "name": name,
        "role": role,
        "type": "session",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=_TTL_MIN)).timestamp()),
    }
    return jwt.encode(payload, _SECRET, algorithm=_ALG)


def decode_session_jwt(token: str) -> Optional[dict]:
    try:
        claims = jwt.decode(token, _SECRET, algorithms=[_ALG])
    except JWTError:
        return None
    if claims.get("type") != "session":
        return None
    return claims


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_session_cookies(response, *, jwt_token: str, csrf_token: str) -> None:
    """Seta studia_session (HttpOnly) + studia_csrf (legível p/ double-submit)."""
    max_age = _TTL_MIN * 60
    response.set_cookie(
        SESSION_COOKIE, jwt_token, max_age=max_age, httponly=True,
        secure=_SECURE, samesite="lax", path="/",
    )
    response.set_cookie(
        CSRF_COOKIE, csrf_token, max_age=max_age, httponly=False,
        secure=_SECURE, samesite="lax", path="/",
    )


def clear_session_cookies(response) -> None:
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/")
```

- [ ] **Step 3: Sanidade** — round-trip do JWT:
```bash
./dev.sh shell backend -c "cd /app && python -c '
from security import mint_session_jwt, decode_session_jwt
t = mint_session_jwt(user_id=\"u1\", email=\"a@b.c\", name=\"A\", role=\"admin\")
c = decode_session_jwt(t)
assert c[\"sub\"]==\"u1\" and c[\"role\"]==\"admin\", c
print(\"jwt roundtrip ok\")
'"
```
Expected: `jwt roundtrip ok`.

- [ ] **Step 4: Commit**
```bash
git add backend/requirements.txt backend/security.py
git commit -m "feat(auth): utilitários de JWT de sessão + CSRF (security.py)"
```

---

### Task 2: Backend — endpoints de handoff e logout

**Files:**
- Create: `backend/auth_router.py`
- Modify: `backend/main.py` (incluir o router)

- [ ] **Step 1: Criar `backend/auth_router.py`** — handoff lê a sessão Better Auth (reusa `_extrair_token`/`_carregar_usuario` do `auth.py`, que ficam):
```python
"""Handoff Better Auth → JWT do studIA, e logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from auth import _carregar_usuario, _extrair_token
from database import get_db
from security import (
    clear_session_cookies,
    mint_session_jwt,
    new_csrf_token,
    set_session_cookies,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/handoff")
async def handoff(request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    """Valida a sessão Better Auth (1 hit no banco) e emite o JWT + CSRF."""
    token = _extrair_token(request)
    user = await _carregar_usuario(token, db) if token else None
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "sessão inválida")
    if user.banned:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "conta suspensa")
    jwt_token = mint_session_jwt(
        user_id=user.id, email=user.email, name=user.name, role=user.role
    )
    set_session_cookies(response, jwt_token=jwt_token, csrf_token=new_csrf_token())
    return {"id": user.id, "email": user.email, "name": user.name, "role": user.role}


@router.post("/logout")
async def logout(response: Response):
    clear_session_cookies(response)
    return {"ok": True}
```

- [ ] **Step 2: Registrar no `main.py`** — após os outros `include_router`, adicione:
```python
from auth_router import router as auth_router  # noqa: E402
app.include_router(auth_router)
```

- [ ] **Step 3: Validar** — a rota existe:
```bash
docker exec studia-backend-dev sh -lc 'cd /app && python -c "
from main import app
print([r.path for r in app.routes if \"/api/auth/\" in getattr(r,\"path\",\"\")])
"'
```
Expected: inclui `/api/auth/handoff` e `/api/auth/logout`.

- [ ] **Step 4: Commit**
```bash
git add backend/auth_router.py backend/main.py
git commit -m "feat(auth): endpoints /api/auth/handoff e /logout (emite/limpa JWT)"
```

---

### Task 3: Backend — validação por JWT (zero DB) + middleware CSRF

**Files:**
- Modify: `backend/auth.py` (`get_current_user_opt` passa a decodificar o JWT)
- Modify: `backend/main.py` (middleware CSRF)

- [ ] **Step 1: Reescrever `get_current_user_opt` em `auth.py`** — decodifica o JWT, zero DB. Mantenha `_extrair_token`, `_carregar_usuario`, `CurrentUser`, `require_user`, `require_admin` como estão (o handoff usa `_carregar_usuario`). Troque APENAS o corpo de `get_current_user_opt`:
```python
from security import SESSION_COOKIE, decode_session_jwt


async def get_current_user_opt(request: Request) -> Optional[CurrentUser]:
    """Usuário atual a partir do JWT de sessão (zero I/O no banco). None se ausente/inválido."""
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    claims = decode_session_jwt(raw)
    if not claims:
        return None
    return CurrentUser(
        id=claims["sub"],
        email=claims.get("email", ""),
        name=claims.get("name", ""),
        role=claims.get("role", "user"),
        banned=False,  # banimento é checado no handoff (na emissão do JWT)
    )
```
Note: `get_current_user_opt` não recebe mais `db: AsyncSession`. Remova o parâmetro `db` da assinatura e o `Depends(get_db)`. Os dependentes (`require_user`, `require_admin`) não mudam (dependem de `get_current_user_opt`).

- [ ] **Step 2: Adicionar middleware CSRF no `main.py`** — double-submit em mutações, exceto handoff/logout. Coloque após `app = FastAPI(...)` e antes/depois do CORS (ordem: CORS deve envolver tudo; adicione o CSRF como `@app.middleware("http")`):
```python
from security import CSRF_COOKIE, SESSION_COOKIE

_CSRF_EXEMPT = {"/api/auth/handoff", "/api/auth/logout"}
_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def csrf_protect(request, call_next):
    if (
        request.method in _MUTATING
        and request.url.path not in _CSRF_EXEMPT
        and request.cookies.get(SESSION_COOKIE)  # só exige CSRF p/ sessão JWT
    ):
        header = request.headers.get("x-csrf-token")
        cookie = request.cookies.get(CSRF_COOKIE)
        if not header or not cookie or header != cookie:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "csrf inválido"}, status_code=403)
    return await call_next(request)
```

- [ ] **Step 3: Rodar a suíte** — os testes sobrescrevem `get_current_user_opt` via `app.dependency_overrides` (conftest), então a maioria não exercita o JWT real; devem seguir verdes. As mutações nos testes usam o client com override (sem cookie `studia_session`), então o middleware CSRF **não** dispara (a condição `request.cookies.get(SESSION_COOKIE)` é falsa). Confirme:
```bash
./dev.sh test -q
```
Expected: 58 verde. Se algum teste de mutação quebrar por CSRF, é porque ele seta o cookie de sessão — ajuste o teste para mandar o header `X-CSRF-Token` casando com o cookie, OU confirme que o override de auth não seta `studia_session`.

- [ ] **Step 4: Teste novo de auth JWT/CSRF** — criar `backend/tests/test_auth_jwt.py`:
```python
from security import (
    CSRF_COOKIE, SESSION_COOKIE, mint_session_jwt, new_csrf_token,
)


def test_jwt_protege_e_csrf(client, auth_state):
    # Desliga o override de auth para exercitar o caminho real do JWT.
    from auth import get_current_user_opt
    from main import app
    app.dependency_overrides.pop(get_current_user_opt, None)
    try:
        # Sem cookie → endpoint protegido dá 401.
        r = client.get("/api/q/stats/dashboard")  # troque por um GET protegido real
        assert r.status_code == 401
        # Com JWT válido → 200; e mutação sem CSRF → 403.
        jwt_token = mint_session_jwt(user_id="admin-1", email="a@b.c", name="A", role="admin")
        csrf = new_csrf_token()
        client.cookies.set(SESSION_COOKIE, jwt_token)
        client.cookies.set(CSRF_COOKIE, csrf)
        r2 = client.post("/api/q/0/favoritar")  # mutação protegida real; sem header CSRF
        assert r2.status_code == 403  # csrf inválido
    finally:
        app.dependency_overrides[get_current_user_opt] = lambda: auth_state["user"]
```
> Ajuste os paths (`/api/q/stats/dashboard`, `/api/q/0/favoritar`) para um GET e um POST protegidos que existam de fato; o objetivo é provar: sem JWT → 401; com JWT mas sem CSRF numa mutação → 403. Rode `./dev.sh test backend/tests/test_auth_jwt.py -v` e itere até passar.

- [ ] **Step 5: Commit**
```bash
git add backend/auth.py backend/main.py backend/tests/test_auth_jwt.py
git commit -m "feat(auth): validação por JWT (zero DB) + middleware CSRF double-submit"
```

---

### Task 4: Frontend — `lib/api.ts` com CSRF + interceptor de handoff

**Files:**
- Modify: `fontend/lib/api.ts`

- [ ] **Step 1: Enriquecer `lib/api.ts`** — adicionar leitor de cookie, `ensureHandoff()` com guard anti-loop, header CSRF em mutações e retry-em-401 dentro do `apiFetch`:
```typescript
function readCookie(name: string): string | null {
  if (typeof document === "undefined") return null;
  const m = document.cookie.match(new RegExp("(?:^|; )" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : null;
}

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);
let handoffInFlight: Promise<void> | null = null;

async function ensureHandoff(): Promise<void> {
  if (!handoffInFlight) {
    handoffInFlight = fetch(apiUrl("/api/auth/handoff"), {
      method: "POST",
      credentials: "include",
    }).then(() => undefined).finally(() => { handoffInFlight = null; });
  }
  return handoffInFlight;
}

function withCsrf(init: RequestInit): RequestInit {
  const method = (init.method || "GET").toUpperCase();
  if (!MUTATING.has(method)) return init;
  const csrf = readCookie("studia_csrf");
  return { ...init, headers: { ...(init.headers || {}), ...(csrf ? { "X-CSRF-Token": csrf } : {}) } };
}

export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const doFetch = () => fetch(apiUrl(path), { credentials: "include", ...withCsrf(init) });
  let res = await doFetch();
  if (res.status === 401) {
    // JWT ausente/expirado: faz o handoff (mint) e tenta de novo, uma vez.
    await ensureHandoff();
    res = await doFetch();
  }
  return res;
}
```
Mantenha `API_BASE`, `apiUrl`, `ApiError`, `apiJson`, `apiPost` — `apiJson`/`apiPost` já chamam `apiFetch`, então herdam CSRF + retry de graça.

- [ ] **Step 2: Handoff proativo no load** — para evitar o 401-then-retry na primeira ação, dispare o handoff uma vez quando o usuário estiver logado. No provider/layout client de nível alto (onde `authClient`/`useSession` está disponível), adicione um `useEffect` que chama `ensureHandoff()` (exporte-a do `lib/api.ts`) ao montar, se houver sessão. (Opcional, mas melhora a UX; o interceptor cobre o caso preguiçoso.)

- [ ] **Step 3: Build do front sem erro de tipos**:
```bash
./dev.sh shell frontend -c "pnpm -s lint" || true
docker exec studia-frontend-dev sh -lc "cd /app && pnpm -s tsc --noEmit" 2>&1 | tail -20
```
Expected: sem erros novos em `lib/api.ts`.

- [ ] **Step 4: Commit**
```bash
git add fontend/lib/api.ts
git commit -m "feat(auth-front): apiFetch com CSRF automático + interceptor handoff em 401"
```

---

### Task 5: Frontend — migrar `fetch()` cru para `apiFetch`

Todos os pontos que falam com o backend precisam passar pelo `apiFetch` (senão mutações tomam 403 por falta de CSRF, e 401 não auto-recupera).

**Files (migrar `fetch(\`${API|API_URL}/...\`)` → `apiFetch("/...")`):**
`app/jobs/page.tsx`, `app/painel/PainelClient.tsx`, `app/disciplinas/page.tsx`, `app/disciplinas/[slug]/page.tsx`, `app/disciplinas/[slug]/aulas/[id]/page.tsx`, `app/flashcards/page.tsx`, `app/flashcards/novo/page.tsx`, `app/flashcards/[id]/page.tsx`, `app/concorrencia/page.tsx`, `app/components/AulaChat.tsx`, `app/q/caderno/[id]/page.tsx`, `app/q/caderno/[id]/annotations/api.ts`, `app/q/filtrar/page.tsx`, `app/q/guias/page.tsx`, `app/q/guias/[id]/page.tsx`, `app/q/cadernos/page.tsx`, `app/q/coletar/page.tsx`, `app/q/coletar/GuiasPanel.tsx`, `app/q/questao/[id]/page.tsx`.

- [ ] **Step 1: Migração mecânica por arquivo.** Em cada arquivo:
  - Remover o `const API = process.env.NEXT_PUBLIC_API_URL || ...` local; importar `import { apiFetch, apiJson, apiPost } from "@/lib/api"` (ou caminho relativo equivalente).
  - Trocar `fetch(\`${API}/api/...\`, init)` por `apiFetch("/api/...", init)` (o `apiFetch` já põe `credentials:"include"`, CSRF e retry). Para GETs que faziam `await fetch(...).then(r=>r.json())`, pode usar `apiJson("/api/...")`. Para POSTs de JSON, `apiPost("/api/...", body)`.
  - **Atenção a uploads** (`FormData`, ex. import de .md/PDF/concursos): NÃO setar `Content-Type` manualmente (o browser põe o boundary). `apiFetch("/api/...", { method: "POST", body: formData })` funciona — o CSRF entra como header, o body FormData fica intacto.
  - `AulaChat.tsx` usa **SSE/stream** (POST que retorna stream): manter via `apiFetch` (não `apiJson`) e ler `res.body` como hoje.

- [ ] **Step 2: Garantir que não sobrou fetch cru ao backend.** Run:
```bash
cd fontend && grep -rn "fetch(\`\${API" app | grep -v "/api/auth" || echo "OK — nenhum fetch cru ao backend"
```
Expected: vazio (ou só chamadas a `/api/auth` do Better Auth, que são same-origin no Next e não usam o backend FastAPI).

- [ ] **Step 3: Smoke manual em dev** — subir o app, logar, e exercitar 1 leitura + 1 mutação (favoritar uma questão) + 1 upload. Confirmar no Network: a 1ª request faz `/api/auth/handoff` (Set-Cookie `studia_session`/`studia_csrf`), as seguintes vão com `X-CSRF-Token` e sem 401.

- [ ] **Step 4: Commit**
```bash
git add fontend/app
git commit -m "refactor(auth-front): todas as chamadas ao backend via apiFetch (CSRF + handoff)"
```

---

### Task 6: Logout + deploy

**Files:**
- Modify: o componente de logout do frontend (onde chama `signOut` do Better Auth)

- [ ] **Step 1: Logout limpa os cookies do backend também.** No handler de logout do front, antes/depois do `signOut()` do Better Auth, chame `apiFetch("/api/auth/logout", { method: "POST" })` para limpar `studia_session`/`studia_csrf`. (Localize com `grep -rn "signOut" fontend/app fontend/lib`.)

- [ ] **Step 2: Suíte + lint finais**:
```bash
./dev.sh test -q          # 58+ verde (inclui test_auth_jwt)
cd fontend && pnpm -s lint
```

- [ ] **Step 3: Env de prod** — adicionar `STUDIA_JWT_SECRET` (valor forte e aleatório) ao `.env` de produção (`/opt/studia/.env`) ANTES do deploy, senão o backend usa o fallback de dev (inseguro). Gerar: `python -c "import secrets;print(secrets.token_urlsafe(48))"`.

- [ ] **Step 4: Commit + deploy** (deploy só com aprovação do dono):
```bash
git add fontend
git commit -m "feat(auth-front): logout limpa cookies de sessão do backend"
git push origin main
./build.sh
```
Após o deploy: confirmar `curl -s -o /dev/null -w '%{http_code}' https://studia.witdev.com.br/api/health` → 200, logar no app e exercitar uma mutação (deve passar via handoff+CSRF, sem 401 persistente).

---

## Self-Review

- **Cobertura do §7 da spec:** Better Auth → handoff ✓ (Task 2); JWT em cookie HttpOnly, validação stateless zero-DB ✓ (Tasks 1,3); CSRF double-submit em mutações ✓ (Task 3,4); sem bearer ✓ (só cookies); renovação via re-handoff no 401 ✓ (Task 4 interceptor).
- **Sem lockout:** o interceptor faz handoff no 1º 401; deploy atômico de front+back; blip de rolling-update documentado (resolve com refresh).
- **Placeholders:** código real nas partes críticas (security.py, auth_router.py, get_current_user_opt, middleware CSRF, apiFetch). A Task 5 é migração mecânica uniforme com lista de arquivos + padrão exato + casos especiais (FormData, SSE).
- **Riscos conhecidos:**
  - (a) `get_current_user_opt` perdeu o parâmetro `db` — qualquer lugar que o chamasse passando `db` quebra; a busca por usos deve confirmar que só é usado via `Depends`.
  - (b) Banimento: agora só é checado no handoff (emissão). Um usuário banido após emitir o JWT continua válido até o token expirar (≤30 min). Aceitável; se precisar de revogação imediata, é um follow-up (blocklist em Redis).
  - (c) CSRF middleware só dispara quando há cookie `studia_session` — endpoints públicos (se houver POST público no backend) seguem sem CSRF; confirmar que cadastro/login passam pelo Next (`/api/auth/*`), não pelo FastAPI.

## Notas

- TTL do JWT: 30 min (`STUDIA_JWT_TTL_MIN`). O interceptor re-handoffa transparentemente ao expirar, enquanto a sessão Better Auth (30 dias) existir.
- `STUDIA_COOKIE_SECURE=false` em dev (HTTP); em prod fica `true` (HTTPS via Traefik).
- Banimento imediato / refresh-token rotativo: follow-ups fora deste plano.

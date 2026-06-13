# studIA — Padrão Arquitetural (Conformidade)

**Data:** 2026-06-13
**Status:** Martelo batido (decisões fechadas pelo dono).
**Escopo:** Define o estado final obrigatório da arquitetura do studIA e de
qualquer **app-irmão single-user** que nasça sob a stack WitDev compartilhada
(ex.: o app de mercado/IBKR).

---

## 1. Papel desta doc

Fixa o desenho oficial e serve como critério de conformidade. Se houver conflito
entre esta doc e qualquer workaround, comentário em código, PR antigo ou
implementação transitória, **esta doc vence**.

Esta doc **não** descreve a `witdev-platform-core` (que é multi-produto e
multi-tenant). Ela descreve o padrão **single-user** que o studIA segue e que
apps-irmãos independentes reusam, compartilhando apenas infraestrutura.

---

## 2. Princípio

- Mesma **stack validada** + **infra compartilhada** da rede docker `minha_rede`.
- **NÃO multi-tenant**: 1 usuário comum + 1 admin (o dono). Sem Tenant /
  Membership / Subscription / Product gating.
- Apps-irmãos (studIA, app de mercado, …) coexistem **independentes** em
  identidade, UX, rotas e build; compartilham **só infra**.
- Compartilhar infra **≠** compartilhar dados: cada app é isolado no seu próprio
  database/prefixo.

---

## 3. Stack oficial

| Camada | Tecnologia | Papel |
|---|---|---|
| Frontend | Next.js 16 (App Router) + React 19 + Tailwind 4 | UI, navegação, SSR/RSC, login/logout, handoff |
| Server state | React Query v5 | queries, mutations, cache e invalidação |
| Backend | FastAPI | regra de negócio, APIs, webhooks, SSE, IA |
| Contratos | Pydantic v2 | validação e schemas |
| Persistência | SQLAlchemy 2.x async | ORM oficial |
| Migrations | Alembic | autoridade única de schema |
| Banco | PostgreSQL + pgvector | instância **compartilhada**, 1 database por app |
| Assíncrono | TaskIQ sobre **NATS** (broker) + **Redis** (result backend / cache / locks / schedules) | filas, workers, scheduler |
| Realtime | SSE via Redis pub/sub | streaming ao browser |
| Storage | MinIO / S3 compartilhado | arquivos e artefatos |
| IA | **LLM proxy WitDev** (LiteLLM) | única porta de IA (modelos, fallback, custo) |

---

## 4. Infra compartilhada (rede `minha_rede`)

Todos os apps single-user falam com os mesmos serviços de infra, isolando-se por
namespace:

- **PostgreSQL** (instância compartilhada): **1 database por app** (`studia`,
  `<app-mercado>`, …).
- **Redis** (compartilhado): prefixo de chave por app (`studia:*`) + DB index
  próprio por app.
- **NATS** (compartilhado): subjects/streams com prefixo por app.
- **MinIO/S3** (compartilhado): bucket ou prefixo por app.
- **LLM proxy WitDev** (compartilhado): único ponto de IA.

**Regra:** nenhum app sobe seu próprio Postgres/Redis/NATS/MinIO isolado. Tudo
roda na infra de `minha_rede`.

---

## 5. Banco

- **1 database físico por app** na instância compartilhada.
- **Sem** schemas lógicos multi-tenant; `search_path` default (`public`).
- **Alembic** é a autoridade única de schema. O `migrate.py` caseiro
  (auto-ALTER) está **aposentado**.
- `pgvector` habilitado via migration.

---

## 6. Identidade (single-user)

- Tabela `user` (Better Auth) com `role ∈ {user, admin}`.
- **1 admin = o dono.** Cadastro de usuário comum é simples.
- **Sem** Tenant / Membership / Subscription / Product. Multi-tenant é
  anti-pattern aqui (YAGNI).

---

## 7. Auth — cookie-JWT stateless, sem bearer (OBRIGATÓRIO)

Fluxo oficial (padrão validado, adaptado do platform-core):

```text
Better Auth (Next)        → login + sessão web (cookie; tabela no Postgres do app)
  → handoff server-side    (route handler Next: lê sessão Better Auth)
  → FastAPI emite JWT curto: cookie HttpOnly `studia_session` + cookie `studia_csrf`
  → browser consome FastAPI direto (credentials:"include" + X-CSRF-Token)
  → FastAPI valida por decode (jose) — ZERO I/O no banco por request
```

**Regras:**

- **Proibido bearer / header `Authorization`** exposto ao browser. Motivo: um
  bearer capturável poderia ser reusado como API de scraper. Só cookie HttpOnly
  + CSRF.
- Login bate no banco **1x** (Better Auth). Validação **por request nunca** bate
  no banco — é decode de JWT.
- Gating por claim `role` (admin vs user).
- Renovação: em 401/expiração, o front **refaz o handoff** (lê a sessão Better
  Auth e re-emite o JWT) — interceptor de auto-recovery, igual ao platform-core.
- JWT assinado com o secret do app; TTL curto.

---

## 8. Assíncrono

- **TaskIQ broker = NATS.** Subjects `taskiq.<app>.{critical,high,default,low}`,
  stream `TASKIQ_<APP>`, DLQ próprio (opcional no início).
- **Redis = result backend + cache + locks + schedules** (prefixo `<app>:`).
- Worker + scheduler por app.
- **SSE** via Redis pub/sub, canal `sse:<app>:*`, escopo por usuário.

---

## 9. IA via proxy (OBRIGATÓRIO)

- Toda chamada de IA passa pelo **LLM proxy WitDev** (consolida modelos,
  fallback e custo). Pede-se o modelo; o proxy domina provider/API.
- **Proibido** SDK de provider direto no app (`google-genai`, `openai`,
  `anthropic`).
- Contratos estruturados via schemas explícitos.

---

## 10. Domain system (backend)

- `platform_core/` fino: `app`, `config`, `db`, `auth`, `ai`, `tasks`,
  `middleware`.
- `domains/<x>/`: `router` · `models` · `schemas` · `services` · `tasks`.
- Registro por convenção/lista; o app é montado iterando os domínios (substitui
  os `include_router` na unha do `main.py`).
- **Padrão de endpoint:** service → router fino → schema Pydantic explícito →
  sessão SQLAlchemy injetada.

---

## 11. Frontend

- Next 16 App Router + React 19 + Tailwind 4.
- **React Query v5** governa o server state (queries/mutations/cache/invalidação).
- Client tipado por domínio + hook; **consumo direto do FastAPI**
  (`credentials:"include"` + `X-CSRF-Token` nas mutações).
- **Sem BFF estrutural.** Route handlers em `app/api/*` só para auth
  (`[...all]`, `handoff`, `logout`) e webhooks.

---

## 12. Apps-irmãos

- Cada app pode ser **repo separado** ou **pasta** — à escolha do dono.
- São **independentes** em UX, rotas, build e **identidade** (users por app —
  não há identidade compartilhada entre apps).
- Compartilham **só infra** (instância Postgres, Redis, NATS, MinIO, LLM proxy)
  via `minha_rede`.

---

## 13. Critério de conformidade

Uma implementação só está conforme quando:

- usa FastAPI como fonte única de verdade;
- usa SQLAlchemy 2.x async;
- usa **Alembic** como única autoridade de schema (sem `migrate.py` caseiro);
- usa **auth cookie-JWT stateless, sem bearer**;
- usa **React Query v5** no server state;
- usa **Postgres compartilhado, 1 database por app**;
- usa **NATS** como broker e **Redis** como result backend/cache;
- usa **IA só via LLM proxy WitDev**;
- **não** é multi-tenant.

---

## 14. Anti-patterns proibidos

- `migrate.py` caseiro / `ALTER` ad-hoc no startup;
- bearer / header `Authorization` exposto ao browser;
- SDK de IA de provider direto no app;
- bater no banco para validar sessão **por request**;
- multi-tenant / Tenant-Product gating;
- BFF estrutural no Next;
- subir banco/Redis/NATS/MinIO isolado fora da infra compartilhada.

---

## 15. Migração do studIA atual → padrão (gaps a fechar)

| Item | Hoje | Alvo | Ação |
|---|---|---|---|
| Migrations | `migrate.py` (auto-ALTER) | Alembic | criar Alembic, baseline do schema atual, gerar `versions/` |
| IA | `google-genai` direto (`gemini_service.py`) | LLM proxy | trocar por client do proxy |
| Broker | TaskIQ + Redis (`worker.py`) | TaskIQ + NATS | repontar broker p/ NATS; Redis vira result/cache |
| Banco | DB `studia` isolado | instância compartilhada `minha_rede` | repontar `DATABASE_URL` p/ Postgres compartilhado |
| Auth backend | `SELECT session` por request ([auth.py](../../../backend/auth.py)) | handoff → JWT cookie | implementar handoff + emissão/decode de JWT; parar de ler tabela `session` por request |
| Front | `fetch()` puro | React Query v5 | provider + hooks por domínio |
| Backend | flat (`main.py` + routers soltos) | `domains/` | mover `q_router`/`guias_router`/`billing_router` p/ domínios |

---

## 16. Relacionado (fora deste spec)

- **Gap de auth do jusmonitoria** (vive na `witdev-platform-core`, outro repo):
  aplicar este mesmo padrão cookie-JWT lá. Merece spec próprio.
- **App de mercado (Engine + Screener, IBKR só leitura):** segue este padrão;
  ganha spec de design próprio assim que o dono decidir repo (pasta neste repo
  vs repo separado).

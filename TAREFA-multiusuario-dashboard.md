# TAREFA: Isolamento multiusuário + Dashboard real (studIA)

> **Contexto urgente:** o login multiusuário (e-mail/senha + Google) está no ar e
> com **cadastro público**. Mas todo o subsistema de estudo (cadernos, pastas,
> favoritas, estatísticas) foi construído **single-tenant** (1 admin). Resultado:
> **qualquer conta nova vê os cadernos/pastas e as estatísticas do admin.** É um
> bug de isolamento/privacidade. O Dashboard (`/painel`) é **100% mockado** e
> precisa virar dados reais por usuário.

Idioma: PT-BR. Siga o `CLAUDE.md` do repo (workflow obrigatório commit→push→`./build.sh`;
backend se auto-migra no startup via `db_prepare`; `migrate.py` adiciona colunas
faltantes por `ALTER TABLE`; **nunca** rodar DROP/DELETE/TRUNCATE em prod sem
confirmação explícita).

---

## 1. Diagnóstico (já investigado — file:line reais)

**Camada de auth (sólida, é a ferramenta a usar):** `backend/auth.py`
- `CurrentUser` tem `.id` (string = id do Better Auth), `.email`, `.role`, `.is_admin`.
- `require_user` (401 se deslogado, 403 se banido) e `require_admin` prontos.
- Sessão validada lendo cookie → tabela `session` → `"user"` no mesmo Postgres.

**O que JÁ é por-usuário:**
- `Resolucao.usuario_uid` (String) é gravado no `POST /{questao_id}/responder`
  (`backend/q_router.py:887`, `user.id`). Limite diário usa isso. ✅

**O que está VAZANDO (single-tenant — sem dono e/ou sem filtro):**
- `CadernoQuestoes` (`backend/models.py:419`) — **sem coluna de dono**.
- `GET /cadernos` (`q_router.py:753`), `GET /pastas` (`q_router.py:774`),
  `GET /cadernos/{id}` (`q_router.py:737`), `POST /cadernos` (`q_router.py:680`)
  — **não usam `require_user` nem filtram por usuário** → retornam tudo global.
- Estatísticas: `GET /{questao_id}/estatisticas` (907), `GET /cadernos/{id}/estatisticas`
  (914), `GET /cadernos/{id}/stats-detalhe` (930) — filtram só por `caderno_id`/
  `questao_id`, **nunca por usuário** → somam as `Resolucao` de TODO MUNDO.
- `QuestaoFavorita` (`models.py:405`) — sem dono ("single-tenant"). `_filtro_favoritas`
  é usado na criação de caderno.
- `QuestaoAnotacao` (`models.py:356`) — tem `usuario_id` mas `_annotation_scope`
  (`q_router.py:833`) fixa `usuario_id IS NULL` → single-tenant.

**Catálogo COMPARTILHADO (deve continuar visível a todos):**
- `Questao`, `Guia` (`models.py:438`), `GuiaCaderno` (`models.py:460`) — coletados
  só pelo admin (coleta é admin-only). É o banco de questões/guias que todos estudam.

**Dashboard:** `fontend/app/painel/page.tsx` — arrays hardcoded (linhas ~11–13,
"55h08min", "434 Acertos", "8 dias sem falhar"), **sem nenhum `fetch`**. Não existe
endpoint de dashboard no backend.

---

## 2. Modelo de dados recomendado (CONFIRMAR com o dono antes)

| Recurso | Escopo | Como |
|---|---|---|
| Questões, Guias, GuiaCaderno | **Compartilhado** (catálogo read-only) | sem mudança |
| Cadernos materializados de um guia | **Compartilhado** (estuda via aba Guias) | identificados por estarem ligados a um `GuiaCaderno.caderno_id` |
| Cadernos criados pelo usuário ("Minhas Pastas" / botão NOVO CADERNO) | **Por usuário** | novo `owner_uid` |
| Favoritas, Resoluções, Anotações, tempo/estatísticas, Dashboard | **Por usuário** | filtrar por `usuario_uid == user.id` |

**Decisão a confirmar (afeta migração):** os cadernos globais que já existem
(ex.: "Importados do TC" 129k, "Sem classificação") são do admin. Recomendado:
backfill `owner_uid = <id do admin>` nesses registros (admin continua vendo, os
demais não). Alternativa: tratar `owner_uid IS NULL` como "catálogo compartilhado".

---

## 3. Backend (em `backend/`)

1. **Model:** adicionar `owner_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)`
   em `CadernoQuestoes`. Em `QuestaoFavorita`, adicionar `owner_uid` (String, nullable, index).
   Atualizar o índice único de `QuestaoAnotacao` para escopo por `usuario_id`/uid real.
2. **migrate.py:** garantir auto-add das novas colunas (o `migrate.py` já faz isso por
   detecção; confirme que cobre `cadernos_questoes.owner_uid` e `questoes_favoritas.owner_uid`).
3. **Backfill (idempotente, no `db_prepare`/migrate):** `UPDATE cadernos_questoes SET owner_uid = (SELECT id FROM "user" WHERE role='admin' ORDER BY "createdAt" LIMIT 1) WHERE owner_uid IS NULL;`
   (só se a decisão for "admin dono dos legados"). **NÃO** apagar nada.
4. **POST `/cadernos`:** receber `require_user`, gravar `owner_uid=user.id`.
5. **GET `/cadernos` e `/pastas`:** `require_user`, filtrar `owner_uid == user.id`
   (Minhas Pastas = só os do usuário).
6. **GET `/cadernos/{id}`:** `require_user`. Permitir acesso se `owner_uid == user.id`
   **OU** o caderno faz parte do catálogo compartilhado (existe `GuiaCaderno` com
   `caderno_id == id`). Caso contrário, 404. (Assim o usuário estuda guias compartilhados,
   mas não enxerga caderno privado de outro.)
7. **Estatísticas** (907/914/930) e o `_filtro_favoritas`: adicionar `require_user`
   e filtrar **todas** as `Resolucao` por `Resolucao.usuario_uid == user.id`.
   Favoritas por `owner_uid == user.id`. Anotações por `usuario_id`/uid do usuário
   (trocar o `IS NULL` de `_annotation_scope` e do PUT correspondente).
8. **Novo endpoint Dashboard** — `GET /q/dashboard` (mesmo prefixo do `q_router`),
   `require_user`, **tudo** filtrado por `Resolucao.usuario_uid == user.id`:
   ```json
   {
     "total_horas_segundos": 0,
     "resolvidas": 0, "acertos": 0, "erros": 0, "taxa": 0,
     "por_disciplina": [{"nome","tempo_segundos","acertos","erros","total","pct"}],
     "atividade_recente": [{"data","resolvidas","acertos"}],   // group by dia
     "streak_dias": 0
   }
   ```
   Disciplina = join `Resolucao→Questao→Materia`. Metas semanais / radar de
   habilidades = fase 2 (pode devolver vazio/zero por enquanto). **Estado vazio**
   (usuário novo, zero resoluções) deve retornar zeros/arrays vazios sem erro.

---

## 4. Frontend (em `fontend/`)

1. `app/painel/page.tsx`: trocar os arrays mock por `fetch` ao `GET /q/dashboard`
   com **`credentials: "include"`** e base `NEXT_PUBLIC_API_URL` (dev é cross-origin;
   prod é same-origin via Traefik — ver memória auth-backend-session). Renderizar
   **estado vazio** pra usuário novo (zeros, "comece a estudar").
2. Conferir que as telas de Pastas/Cadernos/Estatísticas (`app/q/...`) enviam
   `credentials:"include"` nos fetch (o backend agora exige `require_user`).
3. Garantir empty states: usuário novo vê "Nenhum caderno ainda" em Minhas Pastas.

---

## 5. Verificação (obrigatória antes de declarar pronto)

Com **duas contas** (A = admin, B = usuário grátis novo):
- B em `/q/cadernos` (Minhas Pastas) → **vazio** (ou só os de B). ✅
- B responde questões → Dashboard e Estatísticas de B mostram **só** os números de B;
  os de A não mudam. ✅
- B continua conseguindo estudar **guias compartilhados** (aba Guias → caderno do guia). ✅
- A continua vendo os cadernos de A. ✅
- Dashboard de usuário recém-criado = tudo zero, sem erro 500. ✅

Fechar com: commit (escopo claro) → push → `./build.sh` → testar em prod com 2 contas.

---

## 6. Cuidados

- É correção de **privacidade**: priorize corretude sobre rapidez.
- Não rode DROP/DELETE/TRUNCATE em prod. Backfill é só `UPDATE ... WHERE owner_uid IS NULL`.
- Backend tem `db_prepare` no startup: se uma coluna faltar, o container falha visível
  (nunca 500 mudo) — então teste o migrate localmente antes do deploy.

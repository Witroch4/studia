# Página da questão por ID interno — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Buscar uma questão por número (TC ou nosso) e abri-la numa página dedicada que exibe o NOSSO id, nunca o do TC.

**Architecture:** Os dois IDs já existem (`Questao.id` nosso, `Questao.id_externo` TC). O endpoint de busca passa a casar os dois números (prioriza o do TC) e devolve sempre o nosso `id`. O card de `/q/filtrar` linka pra `/q/questao/<id>` (rota já existente) em vez de "abrir em caderno". A página da questão exibe `#{id}` no lugar de `Q{id_externo}`.

**Tech Stack:** FastAPI + SQLAlchemy async (backend), Next.js 16 + React 19 + TanStack Query (frontend), pytest.

## Global Constraints

- Idioma da UI e mensagens: Português BR.
- O `id_externo` (TC) NUNCA aparece na tela do aluno — só o `Questao.id` nosso.
- URL da questão: `/q/questao/<nosso_id>` (sem rota curta `/q/<id>`).
- Não há migração de banco — as duas colunas já existem.
- Frontend é `fontend/` (typo intencional). Não persistir resposta na página avulsa.
- Workflow de entrega obrigatório do projeto: pytest + `pnpm lint` → commit → push `origin/main` → `./build.sh`.

---

### Task 1: Backend — busca aceita TC `id_externo` OU nosso `id` (prioriza TC)

**Files:**
- Modify: `backend/q_router.py:1080-1116` (`buscar_questao_externo`)
- Test: `backend/tests/test_buscar_externo.py`

**Interfaces:**
- Consumes: nada novo.
- Produces: `GET /api/q/questoes/buscar-externo/{n}` resolve `n` como `id_externo`
  OU `id`; em colisão prioriza `id_externo`. Resposta inalterada
  (`{found, questao:{id, id_externo, status, gabarito, tipo, banca, materia, preview}, cadernos:[...]}`).

- [ ] **Step 1: Escrever os testes que falham**

Adicionar ao fim de `backend/tests/test_buscar_externo.py`:

```python
@pytest.mark.asyncio
async def test_buscar_por_nosso_id(db_session, client):
    db_session.add(Questao(id=482, id_externo=3412517, status="ATIVA", gabarito="A"))
    await db_session.commit()
    # busca pelo NOSSO id (482), não pelo do TC
    r = (await client.get("/api/q/questoes/buscar-externo/482")).json()
    assert r["found"] is True
    assert r["questao"]["id"] == 482
    assert r["questao"]["id_externo"] == 3412517


@pytest.mark.asyncio
async def test_colisao_prioriza_id_externo(db_session, client):
    # número 777 bate id_externo de A e id de B → deve retornar A
    db_session.add(Questao(id=500, id_externo=777, status="ATIVA", gabarito="A"))
    db_session.add(Questao(id=777, id_externo=999, status="ATIVA", gabarito="B"))
    await db_session.commit()
    r = (await client.get("/api/q/questoes/buscar-externo/777")).json()
    assert r["found"] is True
    assert r["questao"]["id"] == 500
    assert r["questao"]["id_externo"] == 777
```

- [ ] **Step 2: Rodar e verificar que falham**

Run: `cd backend && python -m pytest tests/test_buscar_externo.py -v`
Expected: `test_buscar_por_nosso_id` e `test_colisao_prioriza_id_externo` FALHAM
(`found` vem `False`, pois hoje só casa `id_externo`).

- [ ] **Step 3: Garantir o import de `or_`**

Verificar o topo de `backend/q_router.py`. Se `or_` não estiver no import do
sqlalchemy, adicioná-lo:

Run: `grep -n "from sqlalchemy import" backend/q_router.py`
Se faltar `or_`, incluir na lista (ex.: `from sqlalchemy import ..., or_`).

- [ ] **Step 4: Implementar a busca por ambos**

Em `backend/q_router.py`, trocar a assinatura e o `.where(...)` da função
`buscar_questao_externo`. De:

```python
@router.get("/questoes/buscar-externo/{id_externo}")
async def buscar_questao_externo(
    id_externo: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Busca uma questão pelo `id_externo` (ID do TC) + cadernos do usuário que a contêm."""
    row = (await db.execute(
        select(
            Questao.id, Questao.id_externo, Questao.status, Questao.gabarito, Questao.tipo,
            Banca.sigla.label("banca"), Materia.nome.label("materia"),
            func.substring(Questao.enunciado_md, 1, 240).label("preview"),
        )
        .outerjoin(Banca, Banca.id == Questao.banca_id)
        .outerjoin(Materia, Materia.id == Questao.materia_id)
        .where(Questao.id_externo == id_externo)
    )).mappings().first()
```

Para:

```python
@router.get("/questoes/buscar-externo/{n}")
async def buscar_questao_externo(
    n: int,
    user: CurrentUser = Depends(require_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Busca uma questão por número: casa `id_externo` (TC) OU `id` (nosso),
    priorizando o match por `id_externo`. + cadernos do usuário que a contêm."""
    row = (await db.execute(
        select(
            Questao.id, Questao.id_externo, Questao.status, Questao.gabarito, Questao.tipo,
            Banca.sigla.label("banca"), Materia.nome.label("materia"),
            func.substring(Questao.enunciado_md, 1, 240).label("preview"),
        )
        .outerjoin(Banca, Banca.id == Questao.banca_id)
        .outerjoin(Materia, Materia.id == Questao.materia_id)
        .where(or_(Questao.id_externo == n, Questao.id == n))
        .order_by((Questao.id_externo == n).desc())
        .limit(1)
    )).mappings().first()
```

- [ ] **Step 5: Rodar a suíte e verificar que passa**

Run: `cd backend && python -m pytest tests/test_buscar_externo.py -v`
Expected: os 4 testes PASSAM (2 antigos + 2 novos).

- [ ] **Step 6: Commit**

```bash
git add backend/q_router.py backend/tests/test_buscar_externo.py
git commit -m "feat(q): buscar-externo casa id_externo (TC) OU id (nosso), prioriza TC"
```

---

### Task 2: Frontend — card de busca em `/q/filtrar` abre a questão

**Files:**
- Modify: `fontend/app/q/filtrar/page.tsx` (handler `gerarDaQuestao` ~232-235; comentário ~221; bloco do card ~396-432)

**Interfaces:**
- Consumes: `porId.questao.id` (nosso), `porId.questao.id_externo` (TC, só pra payload de gerar caderno) — do retorno da Task 1.
- Produces: card com botão "Abrir questão" → `/q/questao/<id>`.

- [ ] **Step 1: Exibir o NOSSO id no título do card**

Trocar a linha (~399):

```tsx
                    <span className="font-semibold text-fg">Questão #{porId.questao.id_externo}</span>
```

Por:

```tsx
                    <span className="font-semibold text-fg">Questão #{porId.questao.id}</span>
```

- [ ] **Step 2: Substituir os botões "Abrir em caderno" por "Abrir questão"**

Trocar o bloco (~414-430):

```tsx
                  <div className="mt-3 flex items-center gap-2 flex-wrap">
                    {porId.cadernos && porId.cadernos.length > 0 ? (
                      porId.cadernos.map((c) => (
                        <Link key={c.id} href={`/q/caderno/${c.id}`}
                          className="px-3 py-1 rounded bg-primary/10 text-primary hover:bg-primary/20 text-xs">
                          Abrir em “{c.nome}”
                        </Link>
                      ))
                    ) : (
                      <button
                        onClick={() => gerarDaQuestao(porId.questao!.id, porId.questao!.id_externo)}
                        disabled={gerando}
                        className="px-3 py-1 rounded bg-primary text-on-primary hover:bg-primary/90 disabled:opacity-50 text-xs">
                        {gerando ? "Gerando…" : "Gerar caderno com esta questão"}
                      </button>
                    )}
                  </div>
```

Por:

```tsx
                  <div className="mt-3 flex items-center gap-2 flex-wrap">
                    <Link href={`/q/questao/${porId.questao.id}`}
                      className="px-3 py-1 rounded bg-primary text-on-primary hover:bg-primary/90 text-xs font-semibold">
                      Abrir questão
                    </Link>
                    <button
                      onClick={() => gerarDaQuestao(porId.questao!.id)}
                      disabled={gerando}
                      className="px-3 py-1 rounded bg-primary/10 text-primary hover:bg-primary/20 disabled:opacity-50 text-xs">
                      {gerando ? "Gerando…" : "Gerar caderno com esta questão"}
                    </button>
                  </div>
```

- [ ] **Step 3: Ajustar `gerarDaQuestao` pra nomear o caderno com o nosso id**

Trocar (~232-235):

```tsx
  function gerarDaQuestao(qid: number, idExterno: number) {
    setErroGerar(null);
    gerarMutation.mutate({ nome: `Questão #${idExterno}`, question_ids: [qid] });
  }
```

Por:

```tsx
  function gerarDaQuestao(qid: number) {
    setErroGerar(null);
    gerarMutation.mutate({ nome: `Questão #${qid}`, question_ids: [qid] });
  }
```

- [ ] **Step 4: Atualizar o comentário da detecção de busca (~221)**

Trocar:

```tsx
  // ── Busca por ID (id_externo do TC): se digitar só números em Matéria/assunto ─
```

Por:

```tsx
  // ── Busca por número (id_externo do TC OU nosso id): só números em Matéria/assunto ─
```

- [ ] **Step 5: Lint**

Run: `cd fontend && pnpm lint`
Expected: sem erros novos (sem variável `idExterno`/`c` não usada, sem import `Link` órfão — `Link` segue em uso no botão "Abrir questão").

- [ ] **Step 6: Commit**

```bash
git add fontend/app/q/filtrar/page.tsx
git commit -m "feat(q/filtrar): card abre a questão (/q/questao/<id>) e exibe nosso id"
```

---

### Task 3: Frontend — página `/q/questao/[id]` exibe o nosso id

**Files:**
- Modify: `fontend/app/q/questao/[id]/page.tsx:95-108` (header)

**Interfaces:**
- Consumes: `q.id`, `q.status`, `q.banca?.sigla`, `q.materia?.nome` (já no retorno de `/api/q/{id}`).
- Produces: header com `Questão #{id}`, breadcrumb derivado e badge ANULADA.

- [ ] **Step 1: Trocar o header (breadcrumb chumbado + id do TC)**

Trocar o bloco (~96-104):

```tsx
        <div className="flex-1">
          <div className="text-xs text-fg-faint">
            Estudo › Caderno IDENCAN CIVIL
          </div>
          <div className="font-semibold">
            Questão Q{q.id_externo}{" "}
            {favorita && <span className="text-yellow-400">⭐</span>}
          </div>
        </div>
```

Por:

```tsx
        <div className="flex-1">
          <div className="text-xs text-fg-faint">
            {[q.banca?.sigla, q.materia?.nome].filter(Boolean).join(" · ") || "Questão avulsa"}
          </div>
          <div className="font-semibold flex items-center gap-2">
            Questão #{q.id}
            {q.status === "ANULADA" && (
              <span className="px-2 py-0.5 bg-warning/15 text-warning rounded text-[10px] font-semibold border border-warning/40">
                ANULADA
              </span>
            )}
            {favorita && <span className="text-yellow-400">⭐</span>}
          </div>
        </div>
```

- [ ] **Step 2: Lint**

Run: `cd fontend && pnpm lint`
Expected: sem erros. (`q.id_externo` deixa de ser usado no header, mas segue no
tipo `Questao` e nos atalhos — sem variável órfã.)

- [ ] **Step 3: Commit**

```bash
git add fontend/app/q/questao/[id]/page.tsx
git commit -m "feat(q/questao): header exibe nosso #id + badge ANULADA (sem id do TC)"
```

---

### Task 4: Verificação end-to-end + deploy (workflow obrigatório)

**Files:** nenhuma alteração — validação e entrega.

- [ ] **Step 1: Suíte backend completa**

Run: `cd backend && python -m pytest tests/ -v`
Expected: tudo PASSA (sem regressão).

- [ ] **Step 2: Lint frontend completo**

Run: `cd fontend && pnpm lint`
Expected: sem erros.

- [ ] **Step 3: Push**

Run: `git push origin main`
Expected: push aceito.

- [ ] **Step 4: Deploy produção**

Run: `./build.sh`
Expected: build + push de imagens + db_prepare + `docker stack deploy` sem erro.

- [ ] **Step 5: Smoke em produção**

Após o deploy, abrir `https://studia.witdev.com.br/q/filtrar`, categoria
"Matéria e assunto", digitar `3412517` → card mostra **"Questão #<nosso_id>"** com
badge ANULADA e botão **"Abrir questão"** → clicar abre `/q/questao/<nosso_id>`
exibindo `Questão #<nosso_id>` no topo (sem o número do TC em lugar nenhum).

- [ ] **Step 6: Worktree limpo**

Run: `git status`
Expected: working tree clean.
```

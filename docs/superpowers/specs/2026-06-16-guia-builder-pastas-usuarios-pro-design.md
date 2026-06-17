# Guia Builder + Pastas de usuários + PRO only — design

**Data:** 2026-06-16
**Status:** aprovado

## Objetivo

Permitir que o **admin** crie guias manualmente, montando-os a partir de
cadernos de questões já existentes no sistema (catálogo + cadernos de qualquer
usuário), com uma área dedicada "Pastas de usuários" para navegar/organizar os
cadernos por dono. Cada guia pode ser marcado como **PRO only** (restrito a
contas PRO) por um switch simples.

## Decisões de produto

- **Fonte de cadernos:** todos os cadernos do sistema — catálogo de guias
  (`owner_uid` NULL) + cadernos de qualquer usuário (join `owner_uid → "user"`),
  organizados por usuário.
- **Builder:** página dedicada com busca, multi-seleção entre usuários e
  reordenação por arrastar (a ordem importa num guia).
- **PRO only:** switch por guia, controlado na página `/q/guias` e no detalhe.

## Schema (migração Alembic — head atual `f1a2b3c4d5e6`)

- `guias.tc_guia_id` → **nullable** (guia manual não vem do TC; índice único
  mantido — múltiplos NULL são permitidos no Postgres).
- `guia_cadernos.tc_caderno_id` → **nullable** (vínculo autoritativo do guia
  manual é `caderno_id`).
- `guias.pro_only` → **Boolean NOT NULL** (add com `server_default=false`,
  modelo usa `default=False` — `compare_server_default` está off, sem drift).
- Sem novas tabelas: guia manual referencia `CadernoQuestoes` por
  `GuiaCaderno.caderno_id` (zero duplicação de questões; acesso de aluno já
  liberado por existir o `GuiaCaderno`).

## Backend (`guias_router.py`, `q_router.py`)

- `GET /api/q/guias/usuarios-pastas` (admin): cadernos agrupados por dono e por
  pasta. Nomes/e-mails via `"user"` (best-effort — `_table_exists`; fallback
  para `owner_uid`). Owner NULL → grupo "Catálogo". Cada caderno:
  `{id, nome, total, tc_caderno_id, em_guia}`.
- `POST /api/q/guias/manual` (admin): `{nome, banca?, pro_only?, caderno_ids[]}`
  (ordenados). Cria `Guia` (`tc_guia_id` NULL, `status='done'`, `pro_only`) +
  um `GuiaCaderno` por caderno na ordem recebida, herdando
  `nome/total_questoes/tc_caderno_id`, `status='materialized'`,
  `caderno_id=<id>`. Valida: lista não-vazia (422), todo `caderno_id` existe
  (404).
- `PATCH /api/q/guias/{id}` (admin): generaliza o atual — `nome?` e `pro_only?`
  opcionais. Renomear continua propagando `pasta` dos cadernos.
- **Gate PRO** em `_caderno_acessivel` (q_router): acessível se for dono, OU
  pertence a algum guia **não** pro-only, OU usuário é admin/PRO
  (`acesso_pro_ativo`). Mesmo gate em `salvar_guia`.
- `listar_guias`/`detalhe_guia`: retornam `pro_only` e `bloqueado`
  (= `pro_only` e não admin/PRO). Caderno materializado sem membership TC usa
  `total_questoes` como coletado (barra 100% no guia manual).

## Frontend

- Sidebar (admin): **"Pastas de usuários"** → `/q/admin/pastas`.
- `/q/admin/pastas`: usuários (expansíveis) → pastas → cadernos, com busca;
  multi-seleção entre usuários; painel de selecionados com arrastar-pra-
  reordenar + nome/banca + toggle **PRO only** + "Gerar guia" → redireciona pro
  `/q/guias/[id]`.
- `/q/guias` (admin): botão "Criar guia" + **switch PRO only por card**
  (`stopPropagation`/`preventDefault` no `<Link>`). Badge **PRO** visível a
  todos quando `pro_only`.
- `/q/guias/[id]`: não-PRO num guia pro-only → Estudar/Salvar bloqueado com
  upsell; admin tem o switch PRO no header (ao lado do lápis de renomear).

## Testes (backend, pytest)

- Criar guia manual a partir de cadernos de usuários distintos (referência +
  ordem preservada); guia aparece em listar/detalhe com pct 100%.
- Aluno comum estuda caderno de guia manual (não pro-only).
- PRO-only bloqueia não-PRO em `_caderno_acessivel`/`salvar`; libera PRO/admin.
- `usuarios-pastas` agrupa por dono.
- Validações: lista vazia → 422; caderno inexistente → 404.
- `alembic check` sem drift.

# Coleta em massa de comentários — UX: pausa real + observabilidade + toast

**Data:** 2026-06-27
**Status:** Design aprovado no brainstorm de 2026-06-27. Estende a Fase 2 (já no ar).

## Problema

A coleta em massa de comentários (Fase 2) está no ar, mas três pontos atrapalham o uso:

1. **Pausa não para de verdade.** O worker de comentários (`_processar_unit_comentarios`)
   não checa `paused_by_user`: o `_enqueue_next` enfileira a próxima unit
   incondicionalmente, então a auto-cadeia ignora a pausa. Clicar "Pausar" só impede o
   supervisor de adicionar trabalho novo — a cadeia segue até acabar. (O worker de
   *caderno* já trata isso com `is_caderno_paused`; o de comentários não.)
2. **Pouca visibilidade.** O painel `/q/coletar` mostra contadores secos e
   "Última atualização: -" (vazio). Não dá pra ver o que está acontecendo (qual questão,
   o que deu certo/errado, ritmo).
3. **Alert nativo do navegador.** O disparo usa `window.alert` ("Coleta iniciada…") e o
   import de desempenho usa `window.alert` + `window.prompt` — dialogs nativos feios.

## Decisões (do brainstorm)

- Observabilidade = **feed de eventos rico** a partir do ledger (sem expor logs de container).
- Notificação = **toast** (sonner), não modal.
- Escopo inclui trocar **também o `window.prompt`** do gabarito por um input dialog
  (é dialog nativo, mesma regra "sem dialog nativo do navegador").
- Mantém **ritmo (q/min) + ETA** no feed.
- Regra de copy continua valendo: **nenhuma string de UI cita "TC"/"TecConcursos"/"tec"**.

## A. Pausa real (+ resume de onde parou)

**Continuidade já é garantida pelo design**: cada questão é uma unit no ledger com status
próprio; resume pega a primeira unit `pending`; questões `done` (+ marcador) nunca são
refeitas. Falta só fazer a pausa efetivamente parar a cadeia.

- **Ledger** (`services/scraper/app/tasks/ledger.py`), espelhando os equivalentes de caderno:
  - `is_comentario_paused(session, *, caderno_id) -> bool` — `tc_jobs` `kind='comentarios'`,
    job ativo, `paused_by_user IS TRUE`.
  - `release_comentario_unit_to_pending(session, *, unit_id) -> None` — `UPDATE
    tc_comentario_units SET status='pending', leased_until=NULL, updated_at=now()
    WHERE id=:unit_id`.
- **Worker** (`services/scraper/app/tasks/comentarios.py`): em `_processar_unit_comentarios`,
  logo após o `_lease`, se `is_comentario_paused(caderno_id)` → `release_comentario_unit_to_pending(unit_id)`
  e **retorna `{"status":"paused"}` SEM chamar `_enqueue_next`**. A cadeia morre; a unit fica
  `pending` para o resume. (Hook substituível `_is_paused`/`_release` para testabilidade,
  no mesmo padrão de `_lease`/`_mark_done`/`_enqueue_next`.)
- **Resume**: ao despausar, `_supervisor_tick_comentarios` (que já exclui pausados via
  `list_active_comentario_jobs`) re-enfileira a primeira unit elegível. Sem mudança.

## B. Observabilidade rica em `/q/coletar`

### Backend (`backend/q_router.py`)
- Enriquecer `GET /api/q/coletar/comentario-jobs`: adicionar `created_at` e `updated_at`
  (ISO) por job, e `questao_atual` (o `questao_id` da unit `running`/`queued`, se houver).
- Novo `GET /api/q/coletar/comentario-jobs/{job_id}/eventos?limit=20` (admin): últimas units
  do job por `updated_at desc`, com join em `questoes` para o `id_externo`:
  `{questao_id, id_externo, status, coments_alunos, coments_professores, block_reason,
  last_error, updated_at}`.

### Frontend (`fontend/app/q/coletar/page.tsx`)
- No card de coleta de comentários, botão **"ver detalhes"** (toggle) que, quando aberto,
  busca os eventos (React Query com a mesma cadência de polling) e renderiza:
  - **Questão atual** (de `questao_atual`/primeiro evento `running`).
  - **Feed** das últimas ~15: `Q#{id_externo} · +{alunos}/{prof} · {ícone status} · {hora}`
    (ícones: ✓ done, ⏭ sem comentário, ⛔ bloqueado, ✗ erro).
  - **Falhas/bloqueios** destacados com `block_reason`/`last_error`.
  - **Ritmo + ETA**: `q/min = done_units / minutos_decorridos` (de `created_at`→agora);
    `ETA = (total_units - done_units) / q_por_min`. Exibe "~Xh Ym restantes".
  - **"Última atualização"** preenchida de `updated_at` (corrige o "-" atual).
- Polling para quando o job não está mais ativo (mesmo critério já usado).

## C. Toast (sonner) no lugar do alert/prompt nativo

- Adicionar dependência **sonner** + `<Toaster />` no layout raiz (`fontend/app/layout.tsx`),
  reutilizável no app inteiro.
- Em `fontend/app/q/cadernos/page.tsx`:
  - Trocar todos os `window.alert` por `toast.success(...)` / `toast.error(...)`
    (coleta iniciada; erro ao iniciar; desempenho importado; erro ao importar).
  - Trocar o `window.prompt` (URL/ID do caderno do gabarito) por um **input dialog** bonito
    reutilizando os primitivos de `components/ui/alert-dialog.tsx` (um pequeno
    `PromptDialog` com um `<input>` + Confirmar/Cancelar). O fluxo do botão "↓ Desempenho"
    passa a abrir esse dialog; ao confirmar, extrai o número e segue o import.
  - Mensagens e labels **neutros** (sem "TC"/"tec"): ex. "Cole a URL ou o ID do caderno de
    origem", "Coleta iniciada em background — acompanhe em Coletar".

## Casos de borda

- Pausar com 0 units em voo → nada a soltar; supervisor não re-enfileira; job fica pausado.
- Eventos de um job sem units ainda → lista vazia (card mostra "sem eventos ainda").
- ETA com `done_units=0` ou tempo decorrido ~0 → exibe "—" em vez de dividir por zero.
- `id_externo` nulo numa unit → feed mostra `Q#{questao_id}` (fallback) sem erro.
- Toast em erro de rede → `toast.error` com a mensagem; nunca trava a UI.

## D. Robustez do worker (achados do diagnóstico em prod)

- **JÁ CORRIGIDO em prod** (commit `4e8dca5`, fora deste spec): o worker enfileirava o
  próximo com `enqueue(...)` SEM `isolated_broker=True` → `nats ConnectionClosedError`
  matava o worker e a cadeia só andava por redelivery (~10 min/questão). Fix: passar
  `isolated_broker=True` no `_enqueue_next` (espelha o worker de caderno). Verificado:
  cadeia self-perpetua a ~20–40s/questão.
- **Retry leve de 5xx transitório** (NESTE spec): no worker, uma chamada ao backend que
  retorna 5xx (ex.: 502 durante deploy/carga) hoje marca a unit como `failed` na hora.
  Adicionar um retry curto (ex.: 2 tentativas com backoff de ~3-5s) ANTES de marcar
  `failed`, para não inflar "Falhas" com erros transitórios. Erros 4xx (ex.: 401 sem
  token) continuam falha imediata.

## Fora de escopo

- Logs crus do container no front (decidido: feed estruturado do ledger).
- Substituir alerts/prompts de OUTRAS páginas além de `cadernos/page.tsx` (faz-se quando
  surgirem; o `<Toaster />` no layout já deixa o toast disponível pra elas).
- Cancelar job pela UI (só pausar/retomar, como hoje).

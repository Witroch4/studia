# Cronograma: anuladas evidenciadas e fora das contas — Design

**Data:** 2026-07-01
**Status:** Aprovado (brainstorming) → implementado na mesma sessão
**Contexto:** dashboard do cronograma (2026-06-15) tratava anuladas como
"restantes" eternas: cinza no mapa, conclusão nunca 100%, meta distribuía o
total bruto (ex.: 876) sendo que anuladas não são respondíveis (o quiz já
bloqueia — trava prospectiva, não grava nem pontua).

## Decisão (usuário)

**Marcar visualmente + tirar das contas.** Total efetivo = total − anuladas
alimenta meta/KPIs/plano; anuladas aparecem em âmbar no mapa e como segmento
próprio no donut. Terceira opção (esconder) rejeitada — o usuário quer VER
que existem.

## Backend

- Regra canônica reusada: `_questao_anulada(status, gabarito)`
  (`q_router.py`) — `status == "ANULADA"` ou gabarito começando com "ANULADA".
- `indice` ganha `anulada: bool` por item (seleciona `Questao.status`).
- `cronograma_router`:
  - `_anuladas_do_caderno(db, cad)` → set de ids anulados do caderno;
  - `total_efetivo = max(total − anuladas, 0)` em `_montar_resposta`, na
    listagem (Planejamento) e no export `.xlsx`;
  - `_resolucoes_distinct(..., ignorar=anuladas)`: resoluções antigas de
    questões depois anuladas saem de resolvidas/acertos/progresso/revisões
    (consistente com "não pontua");
  - resposta ganha `kpis.anuladas`.

## Frontend

- `MapaQuestoes`: 4º estado âmbar (`--warning`), precedência sobre resolução
  antiga; legenda "N anuladas" (só quando N > 0); tooltip/aria "anulada — fora
  da conta".
- `VereditoHero`: subtexto "N anuladas fora da conta" quando N > 0; régua e
  números já chegam efetivos do backend.
- `DistribuicaoDonut`: segmento âmbar "Anuladas" fecha o círculo (caderno
  bruto); % de acerto no centro segue só sobre respondidas.
- Header da página: botão "← Ir ao caderno" (`/q/caderno/{id}`) — navegação
  rápida de volta ao quiz.

## Fora de escopo

- `stats-detalhe` (ErrosPorAssunto) segue contando resoluções históricas.
- Nenhuma migração: sem coluna nova, tudo derivado.

## Testes

- `test_anuladas_fora_das_contas`: caderno 4 questões (2 anuladas — uma por
  status, uma por gabarito), resolução antiga numa anulada → `kpis.total=2`,
  `anuladas=2`, `resolvidas=1`, progresso ignora anulada, meta final = 2.
- `test_indice_marca_anulada`: `indice` marca `anulada: true/false`.

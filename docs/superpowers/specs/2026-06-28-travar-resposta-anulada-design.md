# Travar resposta em questão ANULADA

**Data:** 2026-06-28
**Status:** aprovado (design) — implementação inline

## Problema

Questão ANULADA hoje é respondível e **conta como acerto** (convenção TC antiga:
`"ANULADA" in gabarito → acertou=True`), inflando a estatística e consumindo o
limite diário. O TC não deixa responder anulada. O usuário quer **manter** as
anuladas nos cadernos (colocou de propósito), mas **travar a resposta**.

## Escopo (decidido com o usuário)

- Trava **prospectiva**: anuladas já respondidas antes ficam no histórico (sem
  mexer em dados — opção de "limpar cadernos" foi recusada).
- **Não** mexer em navegação/progresso: a anulada simplesmente fica "não
  resolvida" (escolha "mínimo"). `próxima não resolvida` pode parar nela.
- Aplicar tanto na tela do caderno quanto na página avulsa `/q/questao/[id]`.

## Detecção de anulada

`status == "ANULADA"` OU `"ANULADA" in (gabarito or "").upper()`.

## Mudanças

### 1. Backend — `POST /api/q/{id}/responder` não pontua anulada

`backend/q_router.py` (função `responder`, ~1355). Logo após o `404` de questão
inexistente e **antes** da idempotência/limite, retornar early se anulada:

```python
    anulada = (q.status == "ANULADA") or ("ANULADA" in (q.gabarito or "").upper())
    if anulada:
        total = (await db.execute(select(func.count()).where(
            Resolucao.questao_id == questao_id, Resolucao.usuario_uid == user.id))).scalar_one()
        acertos = (await db.execute(select(func.count()).where(
            Resolucao.questao_id == questao_id, Resolucao.usuario_uid == user.id,
            Resolucao.acertou == True))).scalar_one()  # noqa: E712
        return {
            "anulada": True,
            "acertou": None,
            "gabarito": q.gabarito,
            "stats": {"resolvidas": total, "acertos": acertos, "erros": total - acertos},
            "limite": await resumo_limite(db, user),
            "meta_diaria": await meta_diaria_status(db, user, era_nova=False),
        }
```

- **Não grava** `Resolucao`, **não chama** `garantir_pode_resolver` (não consome limite).
- Remover o ramo morto `if "ANULADA" in gab: acertou = True` (agora inalcançável)
  → o cálculo de `acertou` começa em `if corretas:`.

### 2. Frontend — tela do caderno (`fontend/app/q/caderno/[id]/page.tsx`)

- `const anulada = questao.status === "ANULADA";`
- Alternativas: `disabled={resolvida || anulada}`.
- Botão "Resolver Questão": render só quando `!resolvida && !anulada`.
- `resolverQuestao()`: adicionar `|| anulada` no guard de saída.
- Quando `anulada`, exibir aviso no lugar do botão:
  `⚠ Questão anulada — não pode ser respondida e não conta na sua estatística.`
- Bônus de coerência: cabeçalho mostra `#{questao.id}` (nosso) no lugar de
  `#{questao.id_externo}` (linha ~662).

### 3. Frontend — página avulsa (`fontend/app/q/questao/[id]/page.tsx`)

- `const anulada = q.status === "ANULADA";`
- Alternativas: `disabled={resolvida || anulada}`.
- Botão "RESOLVER QUESTÃO": render só quando `!resolvida && !anulada`.
- Quando `anulada`, exibir o mesmo aviso + gabarito (o badge ANULADA já está no header).

### 4. Testes

`backend/tests/test_responder_anulada.py` (novo):
- Responder numa anulada retorna `anulada: true`, `acertou: null` e **não grava** `Resolucao`.
- (Sanidade) responder numa questão normal continua gravando e pontuando.

## Não-objetivos (YAGNI)

- Descontar/remover anuladas já respondidas (recusado).
- Pular anuladas na navegação ou no contador de progresso.
- Destacar a alternativa "correta" de uma anulada (não há gabarito de letra).

## Verificação / entrega

`pytest tests/ -v` + `pnpm lint` → commit → push → `./build.sh` → smoke em prod.

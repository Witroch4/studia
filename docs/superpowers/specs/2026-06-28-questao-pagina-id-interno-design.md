# Página da questão por ID interno + busca por número (TC ou nosso)

**Data:** 2026-06-28
**Status:** aprovado (design) — pronto para plano de implementação

## Problema

No `/q/filtrar`, ao digitar o número de uma questão, o card de resultado oferece
botões "Abrir em Caderno X" que abrem o caderno **na questão 1**, não a questão
buscada. Além disso, a tela exibe o `id_externo` (ID do TC, ex. `3412517`) como se
fosse o código da questão para o aluno.

O usuário quer:

1. Um link **clicável que abre a própria questão** numa página dedicada
   (ex. `/q/questao/482`), não "abrir em caderno".
2. **Dois IDs distintos**: um que localiza a questão na origem (TC) e o nosso, que
   é o exibido ao aluno. Exibir sempre **o nosso**, nunca o do TC.

## Descoberta-chave (não precisa de migração)

A tabela `questoes` já tem os dois IDs:

- `Questao.id` — **nosso** (BigInteger, PK autoincrement). Já é por ele que
  `GET /api/q/{id}` (q_router.py:2663) e a rota `/q/questao/[id]` buscam.
- `Questao.id_externo` — **TC** (BigInteger, unique, nullable, indexado).

A rota frontend `/q/questao/[id]` **já existe** e busca via `/api/q/{id}` (nosso id),
mas tem dois defeitos: exibe `Q{id_externo}` (TC) no header e tem breadcrumb chumbado
(`"Caderno IDENCAN CIVIL"`). Ela é um protótipo standalone.

## Escopo (decidido com o usuário)

- **Página da questão:** apenas **visualização correta** — enunciado, alternativas,
  gabarito, status ANULADA e **o nosso id** no topo. NÃO persiste resposta, NÃO tem
  fórum/anotações agora.
- **URL:** mantém `/q/questao/<nosso_id>` (sem rota curta `/q/<id>` — evita conflito
  de roteamento com `/q/filtrar`, `/q/cadernos`, etc.).
- **Busca por número:** aceita **ambos** os números (TC `id_externo` e nosso `id`),
  resolve sempre para o nosso `id` e linka para a página. Em colisão (raríssima),
  **prioriza o match por `id_externo`**.
- **O TC (`id_externo`) fica fora da tela do aluno em todos os pontos.**

## Mudanças

### 1. Backend — `buscar_questao_externo` aceita os dois números

`GET /api/q/questoes/buscar-externo/{n}` (q_router.py:1080). Hoje filtra só por
`Questao.id_externo == n`. Trocar para casar `id_externo == n` **OU** `id == n`,
priorizando o match por `id_externo`:

```sql
WHERE id_externo = :n OR id = :n
ORDER BY (id_externo = :n) DESC
LIMIT 1
```

- Mesma URL (não quebra o frontend), só o `WHERE`/`ORDER BY` muda.
- A resposta já devolve `questao.id` (nosso) — é o que o front usa para o link.
- O path param passa a representar "número genérico"; pode renomear `id_externo` → `n`
  internamente, mantendo o segmento de URL `buscar-externo/{n}`.

### 2. Frontend — card de busca em `/q/filtrar`

Arquivo `fontend/app/q/filtrar/page.tsx` (bloco ~396–430):

- Título `Questão #{porId.questao.id_externo}` → **`Questão #{porId.questao.id}`**.
- **Remover** os links "Abrir em '{caderno}'" (eles caem na questão 1 do caderno).
- Adicionar botão primário **"Abrir questão"** → `<Link href={/q/questao/${porId.questao.id}}>`.
- Manter "Gerar caderno com esta questão" como ação **secundária** (sempre visível,
  não só quando não há cadernos).

### 3. Frontend — página `/q/questao/[id]`

Arquivo `fontend/app/q/questao/[id]/page.tsx`:

- Header (linha ~101): `Questão Q{q.id_externo}` → **`Questão #{q.id}`**.
- Breadcrumb (linha ~98): `"Estudo › Caderno IDENCAN CIVIL"` → derivado
  (`banca.sigla · materia.nome`) com fallback `"Questão avulsa"`.
- Badge **ANULADA** no header sempre que `q.status === "ANULADA"` (hoje só aparece
  após RESOLVER).
- Mantém o resto como está: alternativas, RESOLVER (local, sem persistir), gabarito.

### 4. Testes

`backend/tests/test_buscar_externo.py`:

- Caso novo: achar a questão pelo **nosso `id`**.
- Caso novo: **prioridade** — quando um número bate `id_externo` de uma questão e
  `id` de outra, retorna a do `id_externo`.
- Manter o caso existente de busca por `id_externo`.

## Não-objetivos (YAGNI)

- Persistir a resposta na página avulsa (continua local).
- Fórum / anotações / favoritar de verdade na página avulsa.
- Rota curta `/q/<id>`.
- Navegação ←/→ robusta (segue indo para `id±1`, pode cair em 404 — limitação aceita).
- Exibir o `id_externo` (TC) em qualquer ponto da UI do aluno.

## Verificação / entrega

Workflow obrigatório do projeto: `pytest tests/ -v` no backend + `pnpm lint` no front,
depois commit → push `origin/main` → `./build.sh` (deploy prod) → worktree limpo.

# Concorrência: catálogo público + import privado + guia do CSV

**Data:** 2026-07-02
**Status:** aprovado pelo usuário

## Problema

A página `/concorrencia` importa CSV de resultado de concurso e simula notas de
corte por cotas (Lei 15.142/2025). Hoje:

- Os 5 endpoints (`/api/concursos*`) não têm nenhum gate de auth — qualquer
  requisição importa, simula e **deleta** concursos de qualquer pessoa.
- Os dados são um pool global sem dono (`concursos` não tem `user_id` nem
  visibilidade).
- O padrão de CSV aceito é "documentado" só numa linha de dica no uploader e na
  mensagem de erro do parser.

## Decisões (com o usuário)

1. **Quem importa:** admin importa para o catálogo público; usuário comum também
   importa, mas o concurso fica privado (visível só para ele).
2. **Ensino do padrão CSV:** guia expandível na própria página (painel "Como
   preparar o CSV"). Sem página separada, sem template para download.
3. **Acesso:** livre para todo usuário logado — sem trava PRO/billing.

## Design

### Dados

- Migration Alembic em `concursos`: `user_id` (String, nullable, index) e
  `is_public` (Boolean, NOT NULL, default `false`).
- Backfill dos registros existentes: `is_public = true`, `user_id = NULL`
  (legado do pool global continua visível a todos).
- `models.py`: colunas correspondentes no modelo `Concurso`.

### Regras de acesso (backend `main.py`)

| Endpoint | Regra |
|---|---|
| `POST /api/concursos/import` | Usuário logado. Grava `user_id`. Campo `publico` no form: só admin consegue `true`; para user comum é forçado `false`. |
| `GET /api/concursos` | Públicos + privados do próprio usuário; cada item com flags `publico` e `meu`. |
| `GET /api/concursos/{id}` e `POST /{id}/simular` | Permitido se público, dono ou admin; senão 403. |
| `DELETE /api/concursos/{id}` | Só dono ou admin. |

Helpers já existentes em `backend/auth.py` (`get_current_user`, `is_admin`).

### Frontend (`fontend/app/concorrencia/`)

- Lista dividida: **"Catálogo"** (públicos, badge) e **"Meus concursos"**
  (privados do usuário). Botão de excluir só onde o usuário pode excluir.
- Uploader: admin vê toggle **"Publicar no catálogo"**; user comum importa
  privado sem toggle.
- **Guia expandível "Como preparar o CSV"**: painel com tabela de colunas
  (obrigatórias `PONTOS` e `AC`; opcionais com aliases — `UF`=`POLO`,
  `REGIÃO`=`MACROPOLO` etc.), linhas de exemplo, e a explicação de que
  **AC/PCD/PN/PI/PQ guardam a posição do candidato naquela lista de cota**
  (vazio = não concorre àquela lista).
- React Query mantido; expansão do guia é ação do usuário (não viola a regra de
  layout estável).

### Erros e testes

- Parser inalterado (mensagens já apontam coluna faltante); permissão negada →
  403 com mensagem clara.
- Pytest: visibilidade (user vê público + seu, não vê privado alheio),
  `publico=true` negado a não-admin, delete negado a não-dono.

## Fora de escopo

Billing/PRO, edição de concursos importados, mudanças no motor de simulação
(`concurso_engine.py`).

# studIA — Canvas overlay no card da questão

**Status**: Design aprovado
**Owner**: Wital
**Data**: 2026-06-07

---

## 1. Visão

Adicionar à tela de resolução de questões uma experiência parecida com estudar em PDF: o usuário pode rabiscar, marcar, apagar e limpar anotações sobre a área inteira do card da questão, sem perder o fluxo atual de selecionar alternativa, resolver e navegar.

A decisão aprovada é a opção **overlay no próprio card da questão**:

- O canvas cobre o card inteiro da questão: header, metadados, enunciado, alternativas, botão de resolver e rodapé de navegação.
- Um switch liga/desliga o modo canvas.
- Quando o canvas está desligado, a camada some e o card volta a funcionar normalmente.
- Quando o canvas volta a ligar, os rabiscos salvos reaparecem.
- O duplo clique para riscar item não pertence ao canvas; é comportamento normal da página.
- A calculadora científica abre por botão, com histórico persistido.

Fora do card da questão não entra no MVP. A área da página, sidebar e abas superiores continuam limpas para evitar conflito com navegação global.

---

## 2. Comportamento de UX

### 2.1 Estados

**Canvas desligado**

- A questão funciona como hoje: selecionar alternativa, resolver, navegar e usar atalhos.
- A camada de desenho não aparece e não captura ponteiro.
- Rabiscos existentes ficam ocultos, mas continuam salvos.
- Tachados por duplo clique permanecem visíveis, porque são estado da página, não do canvas.

**Canvas ligado**

- Uma camada transparente cobre o card inteiro da questão.
- O usuário desenha sobre qualquer ponto do card.
- O card abaixo fica visível, mas não recebe clique enquanto o canvas estiver capturando desenho.
- Para voltar a selecionar alternativa ou usar botões do card, o usuário desliga o switch.
- `Esc` pode desligar o canvas como atalho de saída.

### 2.2 Toolbar

A toolbar aparece apenas com o canvas ligado e fica presa ao card:

- Lápis.
- Marca-texto.
- Borracha.
- Limpar canvas.
- Cor do traço.
- Espessura do traço.
- Botão da calculadora científica.

`Limpar canvas` apaga apenas os rabiscos do canvas da questão atual. Não remove tachados.

### 2.3 Tachado por duplo clique

O duplo clique funciona no modo normal da página:

- Dois cliques em uma alternativa alternam o tachado daquela alternativa.
- Dois cliques em um bloco do enunciado alternam tachado naquele bloco quando houver alvo identificável.
- O estado é salvo separadamente dos rabiscos.
- O tachado é visível com canvas ligado ou desligado.

Para evitar comportamento imprevisível no enunciado HTML importado, o MVP deve priorizar alvos estruturados:

- Alternativa inteira.
- Parágrafos principais do enunciado.
- Futuramente, seleção textual fina pode virar destaque/tachado por seleção.

---

## 3. Persistência

Persistência padrão: backend, escopada por usuário + caderno + questão.

Chave lógica:

```text
usuario_id + caderno_id + questao_id
```

Enquanto autenticação/usuário ainda estiver em transição, `usuario_id` pode ser nulo, seguindo o padrão atual de `resolucoes.usuario_id`.

`localStorage` entra apenas como fallback de segurança:

- Guarda alterações ainda não sincronizadas.
- Reenvia quando a API volta.
- Não é a fonte principal de verdade.

### 3.1 Modelo de dados

Tabela proposta:

```sql
CREATE TABLE questao_anotacoes (
  id BIGSERIAL PRIMARY KEY,
  usuario_id INTEGER NULL,
  caderno_id INTEGER NULL REFERENCES cadernos_questoes(id) ON DELETE CASCADE,
  questao_id BIGINT NOT NULL REFERENCES questoes(id) ON DELETE CASCADE,
  canvas_json JSONB NOT NULL DEFAULT '{}',
  strikes_json JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX uq_questao_anotacoes_scope
  ON questao_anotacoes (COALESCE(usuario_id, 0), COALESCE(caderno_id, 0), questao_id);
```

`canvas_json` armazena traços vetoriais, não imagem bitmap. Isso permite redimensionar, apagar e renderizar melhor em telas diferentes.

Formato inicial:

```json
{
  "version": 1,
  "cardSize": { "width": 976, "height": 690 },
  "strokes": [
    {
      "id": "stroke_...",
      "tool": "pen",
      "color": "#22c55e",
      "width": 4,
      "points": [{ "x": 0.21, "y": 0.32, "p": 0.7 }]
    }
  ]
}
```

Os pontos usam coordenadas normalizadas de `0` a `1` relativas ao card, para sobreviver a zoom, fonte maior e tamanhos de tela diferentes.

`strikes_json` armazena alvos tachados:

```json
{
  "version": 1,
  "targets": [
    { "type": "alternative", "id": 12345 },
    { "type": "statement-block", "index": 0 }
  ]
}
```

### 3.2 API

Rotas propostas dentro de `/api/q`:

```http
GET /api/q/cadernos/{caderno_id}/questoes/{questao_id}/annotations
PUT /api/q/cadernos/{caderno_id}/questoes/{questao_id}/annotations
```

Payload do `PUT`:

```json
{
  "canvas_json": {},
  "strikes_json": {}
}
```

O frontend salva com debounce curto após alterações, por exemplo 700 ms, e força flush ao trocar de questão.

---

## 4. Calculadora científica

A calculadora abre por botão na toolbar do canvas e também pode ser usada sem apagar as anotações.

Comportamento:

- Painel flutuante sobre a tela, sem trocar de rota.
- Modo científico: trigonometria, potência, raiz, log, ln, parênteses, porcentagem e memória simples.
- Histórico de contas com expressão, resultado, data e questão/caderno de origem quando aplicável.
- Foco dentro da calculadora suspende hotkeys da questão.

Modelo de histórico:

```sql
CREATE TABLE calculadora_historico (
  id BIGSERIAL PRIMARY KEY,
  usuario_id INTEGER NULL,
  caderno_id INTEGER NULL,
  questao_id BIGINT NULL,
  expression TEXT NOT NULL,
  result TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
```

Implementação deve usar parser matemático seguro. Não usar `eval`.

Rotas:

```http
GET /api/q/calculator/history?caderno_id={id}&questao_id={id}
POST /api/q/calculator/history
DELETE /api/q/calculator/history/{id}
```

---

## 5. Componentes frontend

A rota atual `fontend/app/q/caderno/[id]/page.tsx` concentra muita responsabilidade. Para esta feature, a implementação deve extrair componentes focados:

| Componente | Responsabilidade |
|---|---|
| `QuestionCard` | Renderizar header, enunciado, alternativas, resolver e nav |
| `QuestionCanvasOverlay` | Renderizar e capturar traços sobre o card inteiro |
| `CanvasToolbar` | Switch, lápis, marca-texto, borracha, limpar e calculadora |
| `useQuestionAnnotations` | Buscar, salvar, debounced sync e fallback local |
| `StrikableAlternative` | Alternativa com duplo clique para tachado |
| `StrikableStatement` | Blocos do enunciado com duplo clique quando seguro |
| `ScientificCalculator` | Painel científico e histórico |

O card precisa expor uma `ref` para o overlay medir largura/altura e posicionar o canvas exatamente por cima.

---

## 6. Regras de interação

- Canvas ligado captura `pointerdown`, `pointermove`, `pointerup` e eventos de touch/stylus.
- Canvas desligado usa `pointer-events: none` e fica oculto.
- O switch não apaga dados.
- Trocar de questão força salvamento pendente antes de carregar a próxima.
- Recarregar a página deve restaurar tachados e rabiscos da questão atual.
- Borracha apaga traços vetoriais; o MVP pode apagar o traço inteiro ao tocar nele.
- Marca-texto usa alpha/transparência e não deve impedir leitura.
- Atalhos globais da questão não devem disparar enquanto o usuário desenha ou digita na calculadora.

---

## 7. Estados de erro

- Falha ao carregar anotações: mostrar o card normal e um aviso discreto na toolbar.
- Falha ao salvar: manter alterações no estado local e mostrar indicador "salvamento pendente".
- Conflito de atualização: último salvamento vence no MVP.
- Canvas vazio: `Limpar canvas` fica desabilitado.
- Questão sem `caderno_id`: salvar por `questao_id` com `caderno_id = null`.

---

## 8. Testes

### Backend

- Criar/buscar annotation por caderno + questão.
- Atualizar `canvas_json` sem perder `strikes_json`.
- Atualizar `strikes_json` sem perder `canvas_json`.
- Validar histórico da calculadora.
- Garantir unicidade por usuário + caderno + questão.

### Frontend

- Ativar canvas mostra toolbar e camada por cima do card.
- Desativar canvas devolve clique normal para alternativas.
- Desenhar, desativar e reativar restaura rabiscos.
- Recarregar a página restaura rabiscos.
- Duplo clique em alternativa aplica/remove tachado sem ativar canvas.
- `Limpar canvas` remove rabiscos, mas preserva tachados.
- Calculadora salva expressão no histórico.
- Hotkeys não disparam enquanto calculadora está focada.

### Visual

- Verificar desktop e mobile com Playwright screenshot.
- Verificar que a camada cobre todo o card, não apenas enunciado.
- Verificar que texto e toolbar não se sobrepõem em larguras menores.

---

## 9. Fora do escopo do MVP

- Canvas fora do card da questão.
- Edição textual fina por seleção dentro de qualquer palavra.
- Undo/redo completo dos traços.
- Compartilhamento de anotações entre usuários.
- Exportar questão rabiscada para PDF ou imagem.

Esses itens podem ser adicionados depois sem alterar a decisão central de arquitetura.

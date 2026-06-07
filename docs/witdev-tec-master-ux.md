# witdev-tec-master — UX Reference (capturado do TC ao vivo, 2026-06-06)

Este doc consolida a UX observada no TecConcursos via MCP Playwright DevTools que **adotamos** no `witdev-tec-master`. As decisões abaixo são normativas.

## 1. Filtro facetado (rota `/q/filtrar`)

### 1.1 Sidebar de categorias (12 itens, ordem fixa)

Replicamos a sidebar exata do TC `/questoes/filtrar`:

1. **Matéria e assunto** ⭐ (default ativo)
2. Banca
3. Órgão e cargo
4. Ano
5. Área (Carreira)
6. Escolaridade
7. Formação
8. Região
9. Favoritas
10. Enunciados
11. **Opções** ← chips de filtros ativos (lateral direita)

### 1.2 Toggle "tipo de questão" (topo)

3 opções tipo radio button:

- **Objetivas (todas)** ← default
- Objetivas (inéditas)
- Discursivas

### 1.3 Árvore Matéria → Assunto (a coluna central)

CSS classes do TC que adotamos:

| Classe | Significado |
|---|---|
| `arvore-item` | linha (matéria OU assunto) |
| `arvore-item-pasta` | tem filhos (matéria) |
| `arvore-pasta-expandida` | pasta aberta mostrando assuntos |
| `arvore-item-selecionado` | folha (assunto) selecionada |
| `arvore-item-selecionar-tudo` | "Todo o conteúdo de X" — toggle em massa |
| `arvore-item-bloqueado` | plano free / cotada |

### 1.4 Comportamento de clique (CONFIRMADO ao vivo)

Pasta (matéria com filhos):

| Ação | Resultado |
|---|---|
| **1 clique** | Expande/colapsa (toggle de `arvore-pasta-expandida`) |
| **Sem duplo-clique nativo** | TC não usa `ng-dblclick` — toda interação é click único |

Folha (assunto sem filhos):

| Ação | Resultado |
|---|---|
| **1 clique** | Seleciona/desseleciona o assunto como filtro ativo |

Pseudo-elemento "Todo o conteúdo":

- Quando uma matéria abre, o primeiro item dentro é **"Todo o conteúdo de {matéria}"**
- 1 clique nele = adiciona TODOS os assuntos da matéria como filtros ativos (atalho de massa)

> ⚠️ A pergunta inicial "2 cliques corta o item?" não se confirmou — o TC usa **clique único** + classe CSS toggle. Não há remoção via duplo-clique. Para remover: clique de novo no item (toggle) ou clica no "X" do chip no painel "Opções".

### 1.5 Busca dentro da categoria

Campo "Pesquisar por nome" no topo da árvore — filtra client-side em tempo real (zero requests). Replicamos com `Combobox` virtualizado do shadcn.

### 1.6 Painel direito "Opções"

- Lista chips dos filtros ativos
- Cada chip tem "x" para remover
- Atalhos: "Remover anuladas", "Remover desatualizadas" (DIV `.link-atalho`)

### 1.7 Bottom — contador + ação

```
{N} questões encontradas    [Calcular dificuldade]
Editar quantidades

Nome do caderno: [_____]   Pasta de destino: [▾]
☐ Gerar cadernos em série             [GERAR CADERNO]
```

A contagem é o número mágico (sub-segundo) — vem do `POST /api/q/count` que cacheamos em Redis (ver spec §5.4).

---

## 2. Resolução da questão (rota `/q/questao/{id}`)

### 2.1 Header

```
Estudo > Minhas pastas > {Caderno} > {Caderno}            👁 ⟷ ⏱ 00:01:12
─────────────────────────────────────────────────────────
[Q]uestões  [Ín]dice  Estatísticas  Gabarito  Configurações  Imprimir   Compartilhar
```

### 2.2 Card da questão

```
┌──────────────────────────────────────────────────────────────┐
│ [LOGO]  Questão N de M  (X Resolvidas, Y Acertos, Z Erros) ✕ │
│         Matéria: {nome}                                       │
│         Assunto: {nome}                                       │
├──────────────────────────────────────────────────────────────┤
│ § #ID  BANCA - YYYY - Órgão/Cargo/Área-N-…                ▶ ← →│
├──────────────────────────────────────────────────────────────┤
│           [imagens / fórmulas / enunciado]                    │
│                                                                │
│ Ⓐ alternativa A                                              │
│ Ⓑ alternativa B                                              │
│ Ⓒ alternativa C                                              │
│ Ⓓ alternativa D                                              │
│ Ⓔ alternativa E                                              │
│                                                                │
│ [RESOLVER QUESTÃO]                                            │
│                                                                │
│ ← → 🔀 ⊟ ◀ ▶ ↻ ⭐ ✏️                                          │
│                                                                │
│ ⊘ Encontrou algum erro nesta questão? Fale conosco            │
│ ⓘ Lista das teclas de atalho                                  │
└──────────────────────────────────────────────────────────────┘
```

### 2.3 Atalhos de teclado (CAPTURADOS DO DOM `[tec-click-when-key]`)

**Navegação**

| Tecla | Ação | ng-click |
|---|---|---|
| `←` (37) | Anterior | `vm.questaoAnterior()` |
| `→` (39) | Próxima | `vm.questaoSeguinte()` |
| `L` (76) | Aleatória não resolvida | `vm.questaoAleatoria()` |
| `N` (78) | Próxima não resolvida | `vm.questaoNaoResolvida()` |
| `Z` (90) | Tópico anterior | `vm.questaoDoTopicoAnterior()` |
| `X` (88) | Tópico seguinte | `vm.questaoDoTopicoSeguinte()` |
| `Ctrl+Z` (90) | Desfaz última navegação | `vm.desfazerUltimaQuestao()` |
| `V` (86) | Próxima favorita do caderno | `vm.questaoProximaFavorita()` |
| `U` (85) | Próxima anotada do caderno | `vm.questaoProximaAnotada()` |
| `P` (80) | Ir para… (modal por número) | `vm.abrirQuestaoPorNumero()` |

**Ações na questão**

| Tecla | Ação |
|---|---|
| `M` (77) | Marcar como Favorita |
| `J` | Favoritar direto (sem confirmação) |
| `W` (87) | Alterar anotação |
| `O` (79) | Comentário da questão |
| `F` (70) | Fórum de discussão |
| `H` (72) | Desempenho nesta questão |
| `I` (73) | Detalhes |
| `Y` (89) | Toggle texto associado |
| `Q` (81) | Adicionar questão a caderno |

**UI / preferências**

| Tecla | Ação |
|---|---|
| `+` / `=` (187, 107) | Aumentar fonte |
| `-` (189, 109) | Reduzir fonte |
| `0` (48) | Padrão (fonte) |
| `K` (75) | Alternar modo leitura |
| `.` (190) / `Ctrl+F` (194) | Pausar/retomar relógio |

> **Nosso plano**: implementar via hook `useHotkeys()` mapeando 1:1. Tab do "Lista das teclas de atalho" abre modal com tabela acima.

### 2.4 Diretivas customizadas TC (referência)

Nomes que o TC usa internamente (úteis pra rastrear features):

- `tec-click-when-key="<keycodes>"` — atalho de teclado vinculado a botão
- `tec-flutuar` — sidebar flutuante (offcanvas)
- `tec-tooltip` — tooltip
- `tec-menu-lateral-trigger` — abre menu lateral

Nossa equivalência: shadcn `<Sheet>`, `<Tooltip>`, `<Popover>`, hooks customizados.

---

## 3. Implementação no witdev-tec-master

### 3.1 Componentes Next.js que vamos construir

| Componente | Mapeia | Atalhos |
|---|---|---|
| `<FacetSidebar>` | Coluna esquerda das 12 categorias | — |
| `<ArvoreCategorias>` | Árvore expansível matéria→assunto | — |
| `<ChipsAtivos>` | Painel "Opções" direita | — |
| `<TipoQuestaoToggle>` | Radio Objetivas/Inéditas/Discursivas | — |
| `<QuestaoCard>` | Card central da questão | — |
| `<AlternativasList>` | Lista de alternativas A-E | — |
| `<NavBar>` | ← → 🔀 ⊟ ▶ ↻ etc | 14 atalhos |
| `<TimerRelogio>` | Cronômetro `30:57:24` | `.` |
| `<AtalhosModal>` | Lista oficial atalhos | abre via link |
| `<useHotkeys>` | Hook que registra todos os 25 keydown | central |

### 3.2 Estado (React Query + Zustand)

- **React Query**: `useQ()`, `useContagem(filtros)`, `useCaderno(id)`
- **Zustand**: estado dos filtros ativos, modo leitura on/off, fonte size, relógio paused

### 3.3 Tailwind tokens-base (alinhar studIA)

Reusar os tokens existentes do studIA (`globals.css`): `--primary: #06b6d4`, `--secondary: #8b5cf6`, dark theme.

---

## 4. Diferenças deliberadas vs TC

| Item | TC | witdev-tec-master | Razão |
|---|---|---|---|
| Tecnologia | AngularJS 1.4 | Next.js 16 + React 19 | moderno, type-safe |
| Engine busca | (interno) | Meilisearch 1.11 | open-source, sub-segundo facetas |
| Atalhos | keyCodes legados | `event.key` moderno | `.` ao invés de `190` |
| IA | nenhuma | Gemini comentário/similar | diferencial nosso |
| Embeddings | nenhum | pgvector 768-dim | "questões similares" semântico |
| Resp. mobile | parcial | full responsive | shadcn padrões |

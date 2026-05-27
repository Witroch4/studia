# Guia de Criação de Flashcards - studIA

## Estrutura Básica

Cada flashcard segue este padrão:

```
Flashcard: Tema: Assunto
Frente: [conteúdo da pergunta]
Verso:
[conteúdo da resposta]

Flashcard: Outro Tema: Outro Assunto
Frente: [pergunta]
Verso:
[resposta]
```

---

## Componentes Principais

### 1. **Flashcard: Tema: Assunto**
- **Tema**: Disciplina ou área (ex: "Geotecnia", "Mecânica dos Solos", "Cálculo III")
- **Assunto**: Tópico específico dentro do tema (ex: "Bulbo de Tensões", "Fórmula do Fator Tempo")
- Este header define a categoria e o assunto do card
- **Aparência no app**: Badge cyan no canto superior esquerdo, tag do assunto abaixo

### 2. **Frente: [conteúdo]**
- É a pergunta/questão que aparece no lado da frente do card ao estudar
- Pode conter:
  - Texto em markdown (negrito, itálico, listas)
  - Fórmulas em LaTeX inline: `$T_v$`
  - **Não deve conter tags XML** (use no verso)
- **Dica**: Mantenha conciso, tipo uma pergunta objetiva

### 3. **Verso: [conteúdo]**
- É a resposta/explicação que aparece ao virar o card
- Pode conter **tudo**: markdown, LaTeX, tags XML
- Use para estruturar respostas passo-a-passo ou conceituais
- **Obs**: Deixa uma linha em branco após "Verso:" antes do conteúdo

---

## Tags XML Especiais

As tags XML customizadas são renderizadas com estilos especiais:

### **`<atencao>Titulo: Texto</atencao>`**
- **Uso**: Para alertas, informações críticas, pegadinhas
- **Aparência**:
  - Fundo vermelho sutil (`bg-red-500/8`)
  - Barra vermelha de **3px na esquerda**
  - Texto **"Titulo:"** em **vermelho bold** (#ef4444)
  - Resto do texto em cinza claro
- **Exemplo**:
```
<atencao>Cuidado com a Drenagem ($H_d$):</atencao>
```
- **Renderiza**:
```
┃ Cuidado com a Drenagem (Hd):
```
(com barra vermelha e título em vermelho bold)

### **`<destaque>Texto importante</destaque>`**
- **Uso**: Para destacar conceitos-chave, termos essenciais, palavras que devem ser memorizadas
- **Aparência**:
  - Fundo cyan sutil (`bg-primary/15`)
  - Texto em cyan (`text-primary`)
  - Padding e rounded para destaque inline
- **Exemplo**:
```
O bulbo de tensões define a <destaque>região limite de influência</destaque>.
```

### **`<resumo>Conteúdo destacado</resumo>`**
- **Uso**: Para resumos, fórmulas principais, pontos-chave centralizados
- **Aparência**:
  - Box grande com fundo cyan escuro (`bg-primary/10`)
  - Borda cyan (`border-primary/30`)
  - Texto bold, centralizado e grande
  - Padding generoso
- **Exemplo**:
```
<resumo>
$$T_v = \frac{C_v \cdot t}{H_d^2}$$
</resumo>
```

---

## Markdown Suportado

### **Negrito**
```
**texto em negrito**
```
→ Aparece branco bold

### **Itálico**
```
*texto em itálico*
```
→ Aparece cinza italic

### **Listas com bullet**
```
* Item 1
* Item 2
* Item 3
```
→ Aparece com marcadores cyan

### **Listas numeradas**
```
1. Passo 1
2. Passo 2
3. Passo 3
```

### **Títulos**
```
### Título de Seção
```
→ Aparece branco bold com borda cyan na base

---

## Fórmulas LaTeX

Use `$...$` para **inline** e `$$...$$` para **block**:

### **Inline (dentro do texto)**
```
O Fator Tempo $T_v$ é calculado por...
```

### **Block (em destaque)**
```
<resumo>
$$T_v = \frac{C_v \cdot t}{H_d^2}$$
</resumo>
```

### **Dicas LaTeX**
- Use `\frac{a}{b}` para frações
- Use `\cdot` para multiplicação
- Use `_{subscrito}` para índices: `T_v`, `H_d`, `d_{100}`
- Use `^{expoente}` para potências: `C^2`, `H^2`
- Use `\\` para quebra de linha em blocos
- Use `\sqrt{}` para raiz: `\sqrt{x}`

---

## Estrutura Recomendada para Respostas

### **Modelo 1: Conceitual**
```
Verso:
<resumo>Definição principal</resumo>

**Características:**

* Ponto 1
* Ponto 2
* Ponto 3

<atencao>Observação importante:</atencao>
```

### **Modelo 2: Fórmula + Explicação**
```
Verso:
<resumo>
$$Fórmula = \frac{a}{b}$$
</resumo>

**Termos:**

* **a**: Significado de a
* **b**: Significado de b

<destaque>Ponto crítico sobre a fórmula</destaque>
```

### **Modelo 3: Comparação**
```
Verso:
### Método A

* Característica 1
* Característica 2

### Método B

* Característica 1
* Característica 2

<atencao>Diferença crucial:</atencao>
```

---

## Exemplo Completo

```
Flashcard: Mecânica dos Solos: Fórmula do Fator Tempo ($T_v$)
Frente: Qual é a fórmula do Fator Tempo ($T_v$)? O que representa cada termo?
Verso:

<resumo>
$$T_v = \frac{C_v \cdot t}{H_d^2}$$
</resumo>

**Termos:**

* $T_v$: Fator tempo **(adimensional)**
* $C_v$: Coeficiente de adensamento do solo
* $t$: Tempo decorrido após aplicação da carga
* $H_d$: Maior caminho de drenagem da água

<atencao>Cuidado com a Drenagem ($H_d$):</atencao>

* <destaque>Drenagem Dupla</destaque> (argila entre areias): $H_d = \frac{H}{2}$
* <destaque>Drenagem Simples</destaque> (argila sobre rocha): $H_d = H$

Flashcard: Mecânica dos Solos: Casagrande vs. Taylor
Frente: Qual a escala de tempo em cada método? Qual o ponto notável?
Verso:

### Método de Casagrande

* **Escala:** <destaque>$\log(t)$</destaque> (Logarítmica)
* **Ponto:** $100\%$ de adensamento ($d_{100}$)

### Método de Taylor

* **Escala:** <destaque>$\sqrt{t}$</destaque> (Raiz Quadrada)
* **Ponto:** $90\%$ de adensamento ($d_{90}$)
```

---

## Dicas Práticas

✅ **Faça**:
- Use **negrito** para destacar termos chave
- Use **`<destaque>`** para conceitos que você quer memorizar
- Use **`<atencao>`** para erros comuns e pegadinhas
- Use **`<resumo>`** para fórmulas principais
- Mantenha perguntas **curtas e objetivas**
- Use LaTeX para **qualquer equação ou símbolo matemático**
- Estruture respostas em **seções com títulos**

❌ **Não faça**:
- Não escreva paredes de texto sem estrutura
- Não misture tags (ex: `<atencao><destaque>texto</destaque></atencao>`)
- Não use tags XML na **Frente** (só no Verso)
- Não deixe espaços vazios desnecessários
- Não crie cards muito longos (splitta em dois cards)

---

## Como Usar com IA

Quando pedir para sua IA professor criar flashcards:

```
Crie flashcards no padrão studIA sobre [tema].

Padrão:
- Header: Flashcard: Tema: Assunto
- Frente: Pergunta concisa
- Verso: Resposta estruturada com:
  * <resumo> para fórmulas/definições principais
  * <destaque> para termos importantes
  * <atencao> para alertas/erros comuns
  * Markdown (negrito, listas, títulos)
  * LaTeX para equações: $inline$ e $$block$$

Crie no mínimo X cards sobre...
```

---

## Verificação

Após criar os cards, abra `localhost:3000/flashcards/novo` e teste:

1. ✅ Clique em "Importar Lista"
2. ✅ Cole ou faça upload do arquivo `.md`
3. ✅ Veja o preview de cada card
4. ✅ Verifique se:
   - Tags XML aparecem com as cores corretas
   - Markdown (negrito, listas) renderiza bem
   - Fórmulas LaTeX aparecem formatadas
   - Estrutura é legível

Se algo não aparecer certo, corrija no `.md` e tente de novo!

---

**Agora é com você! Bora estudar! 🚀**

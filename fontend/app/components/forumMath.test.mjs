import assert from "node:assert/strict";
import test from "node:test";

import { normalizeForumMath } from "./forumMath.ts";

test("normaliza barras duplicadas antes de comandos LaTeX dentro de formulas", () => {
  const input = String.raw`* $m = 40\\text{ kg}$

$$Q = m \\cdot c \\cdot \\Delta T$$

$70\\%$

$$Q\_{\\text{total}} = \\frac{Q}{\\eta}$$

$$V\_{\\text{gás}} = \\frac{Q\_{\\text{total}}}{P\_c}$$`;

  const expected = String.raw`* $m = 40\text{ kg}$

$$
Q = m \cdot c \cdot \Delta T
$$

$70\%$

$$
Q_{\text{total}} = \frac{Q}{\eta}
$$

$$
V_{\text{gás}} = \frac{Q_{\text{total}}}{P_c}
$$`;

  assert.equal(normalizeForumMath(input), expected);
});

test("preserva quebras de linha LaTeX intencionais", () => {
  const input = String.raw`$$\begin{aligned} a &= b \\ c &= d \end{aligned}$$`;
  const expected = String.raw`$$
\begin{aligned} a &= b \\ c &= d \end{aligned}
$$`;

  assert.equal(normalizeForumMath(input), expected);
});

test("nao altera barras duplicadas fora de formulas", () => {
  const input = String.raw`Caminho C:\\temp e comando \\text fora da formula.`;

  assert.equal(normalizeForumMath(input), input);
});

test("nao confunde valor monetario antes de formula", () => {
  const input = String.raw`Custo de R$500 e poder calorífico $P\_c$.`;

  assert.equal(normalizeForumMath(input), String.raw`Custo de R$500 e poder calorífico $P_c$.`);
});

test("formata o padrao Gemini usado no forum como blocos matematicos", () => {
  const input = String.raw`Vamos lá! Aplicando os valores do enunciado na fórmula que estruturamos, temos a resolução direta.

### 1. Calcular o calor útil (Energia necessária para a água)

* $m = 40\text{ kg}$ (já que 40 litros de água equivalem a 40 kg)
* $c = 1\text{ kcal/kg}^\circ\text{C}$
* $\Delta T = 60^\circ\text{C} - 20^\circ\text{C} = 40^\circ\text{C}$

$$Q = m \cdot c \cdot \Delta T$$

$$Q = 40 \cdot 1 \cdot 40$$

$$Q = 1.600\text{ kcal}$$

Como o aquecedor tem apenas $70\%$ de eficiência ($\eta = 0,70$), ele precisa gerar mais energia do que a água de fato vai usar.

$$Q_{\text{total}} = \frac{Q}{\eta}$$

Arredondando para duas casas decimais, o consumo é de **$0,57\text{ m}^3$**.

**Gabarito: Letra B**`;

  const output = normalizeForumMath(input);

  assert.match(output, /\$\$\nQ = m \\cdot c \\cdot \\Delta T\n\$\$/);
  assert.match(output, /\$\$\nQ_{\\text{total}} = \\frac{Q}{\\eta}\n\$\$/);
  assert.match(output, /\*\*\$0,57\\text{ m}\^3\$\*\*/);
  assert.doesNotMatch(output, /\\_/);
});

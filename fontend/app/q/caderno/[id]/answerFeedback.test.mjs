import assert from "node:assert/strict";
import test from "node:test";

import { formatAnswerFeedback, formatWrongAnswerFeedback } from "./answerFeedback.ts";

test("mostra somente letras na resposta errada de multipla escolha", () => {
  const feedback = formatWrongAnswerFeedback({
    selecionada: "A",
    gabarito: "C",
    tipo: "MULTIPLA_ESCOLHA",
    alternativas: [
      { letra: "A", texto_md: "Texto da alternativa A", correta: false },
      { letra: "C", texto_md: "Texto da alternativa C", correta: true },
    ],
  });

  assert.equal(feedback, "Você escolheu A, mas o gabarito é C.");
  assert.doesNotMatch(feedback, /Texto da alternativa/);
});

test("mostra certo e errado em questoes CERTO_ERRADO", () => {
  assert.equal(
    formatWrongAnswerFeedback({
      selecionada: "A",
      gabarito: "ERRADO",
      tipo: "CERTO_ERRADO",
      alternativas: [
        { letra: "A", texto_md: "Certo", correta: false },
        { letra: "B", texto_md: "Errado", correta: true },
      ],
    }),
    "Você escolheu Certo, mas o gabarito é Errado.",
  );

  assert.equal(
    formatWrongAnswerFeedback({
      selecionada: "ERRADO",
      gabarito: "CERTO",
      tipo: "CERTO_ERRADO",
      alternativas: [
        { letra: "A", texto_md: "Certo", correta: true },
        { letra: "B", texto_md: "Errado", correta: false },
      ],
    }),
    "Você escolheu Errado, mas o gabarito é Certo.",
  );
});

test("mostra mensagem curta quando o aluno acerta", () => {
  assert.equal(
    formatAnswerFeedback({
      acertou: true,
      selecionada: "A",
      gabarito: "A",
      tipo: "MULTIPLA_ESCOLHA",
      alternativas: [{ letra: "A", correta: true }],
    }),
    "Acertou! Gabarito: A.",
  );

  assert.equal(
    formatAnswerFeedback({
      acertou: true,
      selecionada: "B",
      gabarito: "ERRADO",
      tipo: "CERTO_ERRADO",
      alternativas: [
        { letra: "A", correta: false },
        { letra: "B", correta: true },
      ],
    }),
    "Acertou! Gabarito: Errado.",
  );
});

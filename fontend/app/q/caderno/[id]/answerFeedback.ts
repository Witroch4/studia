export interface AnswerFeedbackAlternative {
  letra: string;
  correta?: boolean | null;
}

export interface WrongAnswerFeedbackInput {
  selecionada: string | null | undefined;
  gabarito: string | null | undefined;
  tipo: string | null | undefined;
  alternativas: AnswerFeedbackAlternative[];
}

export interface AnswerFeedbackInput extends WrongAnswerFeedbackInput {
  acertou: boolean;
}

function clean(value: string | null | undefined) {
  return String(value ?? "").trim();
}

function canonical(value: string | null | undefined) {
  return clean(value)
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase();
}

function isCertoErradoQuestion(input: WrongAnswerFeedbackInput) {
  const tipo = canonical(input.tipo).replace(/[\s-]+/g, "_");
  const gabarito = canonical(input.gabarito);

  return tipo.includes("CERTO_ERRADO") || gabarito === "CERTO" || gabarito === "ERRADO";
}

function formatGenericAnswer(value: string | null | undefined) {
  const trimmed = clean(value);
  const upper = canonical(trimmed);

  if (upper === "CERTO") return "Certo";
  if (upper === "ERRADO") return "Errado";
  if (/^[A-E]$/.test(upper)) return upper;
  return trimmed || "?";
}

function formatCertoErradoAnswer(value: string | null | undefined) {
  const upper = canonical(value);

  if (upper === "A" || upper === "C" || upper === "CERTO") return "Certo";
  if (upper === "B" || upper === "E" || upper === "ERRADO") return "Errado";
  return formatGenericAnswer(value);
}

function formatSelectedAnswer(input: WrongAnswerFeedbackInput) {
  return isCertoErradoQuestion(input)
    ? formatCertoErradoAnswer(input.selecionada)
    : formatGenericAnswer(input.selecionada);
}

function formatExpectedAnswer(input: WrongAnswerFeedbackInput) {
  const correta = input.alternativas.find((alt) => alt.correta === true);

  if (isCertoErradoQuestion(input)) {
    return formatCertoErradoAnswer(input.gabarito || correta?.letra);
  }

  return formatGenericAnswer(correta?.letra || input.gabarito);
}

export function formatWrongAnswerFeedback(input: WrongAnswerFeedbackInput) {
  return `Você escolheu ${formatSelectedAnswer(input)}, mas o gabarito é ${formatExpectedAnswer(input)}.`;
}

export function formatAnswerFeedback(input: AnswerFeedbackInput) {
  if (!input.acertou) return formatWrongAnswerFeedback(input);

  return `Acertou! Gabarito: ${formatExpectedAnswer(input)}.`;
}

type Token =
  | { type: "number"; value: number }
  | { type: "identifier"; value: string }
  | { type: "operator"; value: "+" | "-" | "*" | "/" | "^" | "%" | "!" }
  | { type: "paren"; value: "(" | ")" };

const SUPPORTED_FUNCTIONS = new Set([
  "sin",
  "cos",
  "tan",
  "asin",
  "acos",
  "atan",
  "log",
  "ln",
  "exp",
  "sqrt",
]);
const CONSTANTS: Record<string, number> = { pi: Math.PI, e: Math.E };
const DEG_TO_RAD = Math.PI / 180;
const RAD_TO_DEG = 180 / Math.PI;
const TANGENT_UNDEFINED_TOLERANCE = 1e-12;
// Fatorial: 170! é o maior que cabe em Number (171! = Infinity).
const FACTORIAL_MAX = 170;

export type AngleMode = "deg" | "rad";

export interface EvaluateOptions {
  angleMode?: AngleMode;
}

function userError(message = "Expressão inválida.") {
  return new Error(message);
}

function tokenize(expression: string): Token[] {
  const tokens: Token[] = [];
  let index = 0;

  while (index < expression.length) {
    const char = expression[index];

    if (/\s/.test(char)) {
      index += 1;
      continue;
    }

    if (/\d|\./.test(char)) {
      const start = index;
      let sawDigit = false;
      let sawDot = false;

      while (index < expression.length && /[\d.]/.test(expression[index])) {
        if (expression[index] === ".") {
          if (sawDot) throw userError();
          sawDot = true;
        } else {
          sawDigit = true;
        }
        index += 1;
      }

      if (!sawDigit) throw userError();

      const value = Number(expression.slice(start, index));
      if (!Number.isFinite(value)) throw userError("Número inválido.");
      tokens.push({ type: "number", value });
      continue;
    }

    if (/[a-zA-Z]/.test(char)) {
      const start = index;
      while (index < expression.length && /[a-zA-Z]/.test(expression[index])) {
        index += 1;
      }
      tokens.push({ type: "identifier", value: expression.slice(start, index).toLowerCase() });
      continue;
    }

    if (char === "(" || char === ")") {
      tokens.push({ type: "paren", value: char });
      index += 1;
      continue;
    }

    if (
      char === "+" ||
      char === "-" ||
      char === "*" ||
      char === "/" ||
      char === "^" ||
      char === "%" ||
      char === "!"
    ) {
      tokens.push({ type: "operator", value: char });
      index += 1;
      continue;
    }

    throw userError();
  }

  return tokens;
}

class Parser {
  private index = 0;

  constructor(
    private readonly tokens: Token[],
    private readonly angleMode: AngleMode,
  ) {}

  parse() {
    if (this.tokens.length === 0) throw userError("Digite uma expressão.");

    const value = this.parseAdditive();
    if (this.current()) throw userError();
    return this.ensureFinite(value);
  }

  private parseAdditive(): number {
    let value = this.parseMultiplicative();

    while (this.matchOperator("+") || this.matchOperator("-")) {
      const operator = this.previousOperator();
      const right = this.parseMultiplicative();
      value = operator === "+" ? value + right : value - right;
    }

    return this.ensureFinite(value);
  }

  private parseMultiplicative(): number {
    let value = this.parseUnary();

    while (this.matchOperator("*") || this.matchOperator("/")) {
      const operator = this.previousOperator();
      const right = this.parseUnary();

      if (operator === "/" && right === 0) {
        throw userError("Não é possível dividir por zero.");
      }

      value = operator === "*" ? value * right : value / right;
    }

    return this.ensureFinite(value);
  }

  private parseUnary(): number {
    if (this.matchOperator("+")) return this.parseUnary();
    if (this.matchOperator("-")) return -this.parseUnary();
    return this.parsePower();
  }

  private parsePower(): number {
    const base = this.parsePostfix();

    if (!this.matchOperator("^")) return base;

    const exponent = this.parseUnary();
    return this.ensureFinite(Math.pow(base, exponent), "Resultado fora do limite.");
  }

  private parsePostfix(): number {
    let value = this.parsePrimary();

    // Pós-fixos encadeáveis: % (divide por 100) e ! (fatorial), ex.: 5!!, 50%%.
    for (;;) {
      if (this.matchOperator("%")) {
        value /= 100;
        continue;
      }
      if (this.matchOperator("!")) {
        value = this.factorial(value);
        continue;
      }
      break;
    }

    return value;
  }

  private factorial(input: number): number {
    if (!Number.isInteger(input) || input < 0) {
      throw userError("Fatorial exige inteiro não negativo.");
    }
    if (input > FACTORIAL_MAX) {
      throw userError(`Fatorial suportado até ${FACTORIAL_MAX}.`);
    }
    let result = 1;
    for (let n = 2; n <= input; n += 1) result *= n;
    return this.ensureFinite(result, "Resultado fora do limite.");
  }

  private parsePrimary(): number {
    const token = this.current();
    if (!token) throw userError("Expressão incompleta.");

    if (token.type === "number") {
      this.index += 1;
      return token.value;
    }

    if (token.type === "paren" && token.value === "(") {
      this.index += 1;
      const value = this.parseAdditive();
      if (!this.matchParen(")")) throw userError("Feche os parênteses da expressão.");
      return value;
    }

    if (token.type === "identifier") {
      if (token.value in CONSTANTS) {
        this.index += 1;
        return CONSTANTS[token.value];
      }
      return this.parseFunction(token.value);
    }

    throw userError();
  }

  /** Ângulo de ENTRADA das trig diretas: DEG converte pra radianos. */
  private toRadians(value: number): number {
    return this.angleMode === "deg" ? value * DEG_TO_RAD : value;
  }

  /** Ângulo de SAÍDA das trig inversas: DEG converte de radianos. */
  private fromRadians(value: number): number {
    return this.angleMode === "deg" ? value * RAD_TO_DEG : value;
  }

  private parseFunction(name: string): number {
    if (!SUPPORTED_FUNCTIONS.has(name)) {
      throw userError("Função não suportada.");
    }

    this.index += 1;
    if (!this.matchParen("(")) throw userError("Use parênteses na função.");

    const input = this.parseAdditive();
    if (!this.matchParen(")")) throw userError("Feche os parênteses da função.");

    switch (name) {
      case "sin":
        return this.ensureFinite(Math.sin(this.toRadians(input)));
      case "cos":
        return this.ensureFinite(Math.cos(this.toRadians(input)));
      case "tan": {
        const radians = this.toRadians(input);
        if (Math.abs(Math.cos(radians)) < TANGENT_UNDEFINED_TOLERANCE) {
          throw userError("Tangente indefinida para esse ângulo.");
        }
        return this.ensureFinite(Math.tan(radians));
      }
      case "asin":
        if (input < -1 || input > 1) throw userError("Arco seno exige valor entre -1 e 1.");
        return this.ensureFinite(this.fromRadians(Math.asin(input)));
      case "acos":
        if (input < -1 || input > 1) throw userError("Arco cosseno exige valor entre -1 e 1.");
        return this.ensureFinite(this.fromRadians(Math.acos(input)));
      case "atan":
        return this.ensureFinite(this.fromRadians(Math.atan(input)));
      case "log":
        if (input <= 0) throw userError("Logaritmo exige número positivo.");
        return this.ensureFinite(Math.log10(input));
      case "ln":
        if (input <= 0) throw userError("Logaritmo exige número positivo.");
        return this.ensureFinite(Math.log(input));
      case "exp":
        return this.ensureFinite(Math.exp(input), "Resultado fora do limite.");
      case "sqrt":
        if (input < 0) throw userError("Raiz exige número não negativo.");
        return this.ensureFinite(Math.sqrt(input));
      default:
        throw userError("Função não suportada.");
    }
  }

  private current() {
    return this.tokens[this.index];
  }

  private matchOperator(operator: Extract<Token, { type: "operator" }>["value"]) {
    const token = this.current();
    if (token?.type !== "operator" || token.value !== operator) return false;
    this.index += 1;
    return true;
  }

  private previousOperator() {
    const token = this.tokens[this.index - 1];
    if (token?.type !== "operator") throw userError();
    return token.value;
  }

  private matchParen(paren: "(" | ")") {
    const token = this.current();
    if (token?.type !== "paren" || token.value !== paren) return false;
    this.index += 1;
    return true;
  }

  private ensureFinite(value: number, message = "Resultado inválido.") {
    if (!Number.isFinite(value)) throw userError(message);
    return value;
  }
}

function formatResult(value: number) {
  if (!Number.isFinite(value)) throw userError("Resultado inválido.");
  if (Object.is(value, -0) || value === 0) return "0";

  const abs = Math.abs(value);
  const rounded = abs >= 1e-6 && abs < 1e10 ? Number(value.toFixed(10)) : Number(value.toPrecision(10));
  if (Object.is(rounded, -0) || rounded === 0) return "0";

  return rounded.toString();
}

export function evaluateExpression(expression: string, options: EvaluateOptions = {}): string {
  const parser = new Parser(tokenize(expression.trim()), options.angleMode ?? "deg");
  return formatResult(parser.parse());
}

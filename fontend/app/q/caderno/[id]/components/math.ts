type Token =
  | { type: "number"; value: number }
  | { type: "identifier"; value: string }
  | { type: "operator"; value: "+" | "-" | "*" | "/" | "^" | "%" }
  | { type: "paren"; value: "(" | ")" };

const SUPPORTED_FUNCTIONS = new Set(["sin", "cos", "tan", "log", "ln", "sqrt"]);
const DEG_TO_RAD = Math.PI / 180;
const EPSILON = 1e-12;

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

    if (char === "+" || char === "-" || char === "*" || char === "/" || char === "^" || char === "%") {
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

  constructor(private readonly tokens: Token[]) {}

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

      if (operator === "/" && Math.abs(right) < EPSILON) {
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

    while (this.matchOperator("%")) {
      value /= 100;
    }

    return value;
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
      return this.parseFunction(token.value);
    }

    throw userError();
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
        return this.ensureFinite(Math.sin(input * DEG_TO_RAD));
      case "cos":
        return this.ensureFinite(Math.cos(input * DEG_TO_RAD));
      case "tan": {
        const radians = input * DEG_TO_RAD;
        if (Math.abs(Math.cos(radians)) < EPSILON) {
          throw userError("Tangente indefinida para esse ângulo.");
        }
        return this.ensureFinite(Math.tan(radians));
      }
      case "log":
        if (input <= 0) throw userError("Logaritmo exige número positivo.");
        return this.ensureFinite(Math.log10(input));
      case "ln":
        if (input <= 0) throw userError("Logaritmo exige número positivo.");
        return this.ensureFinite(Math.log(input));
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
  if (Object.is(value, -0) || Math.abs(value) < EPSILON) return "0";

  const abs = Math.abs(value);
  const rounded = abs >= 1e-6 && abs < 1e10 ? Number(value.toFixed(10)) : Number(value.toPrecision(10));
  return rounded.toString();
}

export function evaluateExpression(expression: string): string {
  const parser = new Parser(tokenize(expression.trim()));
  return formatResult(parser.parse());
}

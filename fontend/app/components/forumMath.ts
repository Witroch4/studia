function isEscaped(value: string, index: number) {
  let count = 0;
  for (let i = index - 1; i >= 0 && value[i] === "\\"; i -= 1) {
    count += 1;
  }
  return count % 2 === 1;
}

function findClosingDelimiter(value: string, from: number, delimiter: "$" | "$$") {
  for (let i = from; i < value.length; i += 1) {
    if (delimiter === "$" && (value[i] === "\n" || value[i] === "\r")) {
      return -1;
    }

    if (value.startsWith(delimiter, i) && !isEscaped(value, i)) {
      return i;
    }
  }

  return -1;
}

function normalizeMathBody(value: string) {
  return value
    .replace(/\\\\(?=[A-Za-z%])/g, "\\")
    .replace(/\\_/g, "_");
}

function normalizeMathDelimiters(value: string) {
  let normalized = "";
  let index = 0;

  while (index < value.length) {
    if (value[index] !== "$" || isEscaped(value, index)) {
      normalized += value[index];
      index += 1;
      continue;
    }

    const delimiter: "$" | "$$" = value[index + 1] === "$" ? "$$" : "$";
    const previous = value[index - 1] ?? "";
    const next = value[index + 1] ?? "";
    if (delimiter === "$" && (/\s/.test(next) || /[A-Za-z0-9]/.test(previous))) {
      normalized += value[index];
      index += 1;
      continue;
    }

    const bodyStart = index + delimiter.length;
    const bodyEnd = findClosingDelimiter(value, bodyStart, delimiter);
    if (bodyEnd === -1) {
      normalized += value[index];
      index += 1;
      continue;
    }

    normalized += delimiter;
    normalized += normalizeMathBody(value.slice(bodyStart, bodyEnd));
    normalized += delimiter;
    index = bodyEnd + delimiter.length;
  }

  return normalized;
}

function normalizeSingleLineDisplayMath(value: string) {
  return value.replace(/^([ \t]*)\$\$([^\r\n]+?)\$\$[ \t]*$/gm, (_match, indent: string, body: string) => {
    return `${indent}$$\n${body.trim()}\n${indent}$$`;
  });
}

export function normalizeForumMath(value: string) {
  return normalizeSingleLineDisplayMath(normalizeMathDelimiters(value));
}

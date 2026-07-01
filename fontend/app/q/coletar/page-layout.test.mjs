import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(new URL("./page.tsx", import.meta.url), "utf8");

test("tabela de contas TC usa colunas fixas compartilhadas no desktop", () => {
  const accountSection = source.slice(source.indexOf("Contas TC"));
  const tableStart = accountSection.indexOf("overflow-x-auto");
  const tableEnd = accountSection.indexOf('className="mt-4 grid gap-3', tableStart);
  const tableSource = accountSection.slice(tableStart, tableEnd);

  assert.match(tableSource, /TC_ACCOUNTS_GRID_COLUMNS/);
  assert.doesNotMatch(tableSource, /grid-cols-\[[^\]]*auto[^\]]*\]/);
});

// Extração de imagens do clipboard para o editor do fórum.
//
// "Copiar imagem" no navegador coloca DUAS coisas no clipboard: o blob da
// imagem e um text/html com <img src="url-externa">. O editor precisa priorizar
// o BLOB (que sobe pro MinIO) — a URL externa é bloqueada pelo sanitizador do
// fórum e viraria "[imagem bloqueada]".

const TIPOS_IMG = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);

interface ClipboardLike {
  files?: ArrayLike<File>;
  items?: ArrayLike<{ kind: string; type: string; getAsFile: () => File | null }>;
}

export function imagensDoClipboard(dt: ClipboardLike): File[] {
  const arquivos = Array.from(dt.files ?? []).filter((f) => TIPOS_IMG.has(f.type));
  if (arquivos.length) return arquivos;
  return Array.from(dt.items ?? [])
    .filter((i) => i.kind === "file" && TIPOS_IMG.has(i.type))
    .map((i) => i.getAsFile())
    .filter((f): f is File => f !== null && TIPOS_IMG.has(f.type));
}

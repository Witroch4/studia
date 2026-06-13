import type { AnnotationState, CalculatorHistoryItem, CanvasState, StrikesState } from "./types";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8011";

export async function fetchAnnotations(cadernoId: number, questaoId: number): Promise<AnnotationState> {
  const response = await fetch(`${API}/api/q/cadernos/${cadernoId}/questoes/${questaoId}/annotations`, {
    credentials: "include",
  });
  if (!response.ok) throw new Error(`Falha ao carregar anotacoes: ${response.status}`);
  return response.json();
}

export async function saveAnnotations(
  cadernoId: number,
  questaoId: number,
  canvas_json: CanvasState,
  strikes_json: StrikesState,
): Promise<AnnotationState> {
  const response = await fetch(`${API}/api/q/cadernos/${cadernoId}/questoes/${questaoId}/annotations`, {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ canvas_json, strikes_json }),
  });
  if (!response.ok) throw new Error(`Falha ao salvar anotacoes: ${response.status}`);
  return response.json();
}

export async function fetchCalculatorHistory(cadernoId?: number, questaoId?: number): Promise<CalculatorHistoryItem[]> {
  const params = new URLSearchParams();
  if (cadernoId != null) params.set("caderno_id", String(cadernoId));
  if (questaoId != null) params.set("questao_id", String(questaoId));
  const qs = params.toString();
  const response = await fetch(`${API}/api/q/calculator/history${qs ? `?${qs}` : ""}`, {
    credentials: "include",
  });
  if (!response.ok) throw new Error(`Falha ao carregar historico: ${response.status}`);
  const data = await response.json();
  return data.items || [];
}

export async function createCalculatorHistory(input: {
  expression: string;
  result: string;
  caderno_id: number | null;
  questao_id: number | null;
}): Promise<CalculatorHistoryItem> {
  const response = await fetch(`${API}/api/q/calculator/history`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  if (!response.ok) throw new Error(`Falha ao salvar historico: ${response.status}`);
  return response.json();
}

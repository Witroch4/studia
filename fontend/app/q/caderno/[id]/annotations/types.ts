export type CanvasTool = "pen" | "highlight" | "eraser";

export interface CanvasPoint {
  x: number;
  y: number;
  p?: number;
}

export interface CanvasStroke {
  id: string;
  tool: Exclude<CanvasTool, "eraser">;
  color: string;
  width: number;
  points: CanvasPoint[];
}

export interface CanvasState {
  version: 1;
  cardSize: { width: number; height: number } | null;
  strokes: CanvasStroke[];
}

export type StrikeTarget =
  | { type: "alternative"; id: number }
  | { type: "statement-block"; index: number };

export interface StrikesState {
  version: 1;
  targets: StrikeTarget[];
}

export interface AnnotationState {
  id: number | null;
  caderno_id: number;
  questao_id: number;
  canvas_json: CanvasState;
  strikes_json: StrikesState;
  updated_at: string | null;
}

export interface CalculatorHistoryItem {
  id: number;
  caderno_id: number | null;
  questao_id: number | null;
  expression: string;
  result: string;
  created_at: string | null;
}

export function emptyCanvas(): CanvasState {
  return { version: 1, cardSize: null, strokes: [] };
}

export function emptyStrikes(): StrikesState {
  return { version: 1, targets: [] };
}

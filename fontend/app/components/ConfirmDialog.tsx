"use client";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export type ConfirmState = {
  titulo: string;
  descricao?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** `false` deixa o botão de confirmação na cor primária (ação não-destrutiva). */
  destrutivo?: boolean;
  /** Desabilita o botão de confirmação enquanto a ação roda. */
  carregando?: boolean;
};

/**
 * Diálogo de confirmação padrão studIA — substitui o `window.confirm` nativo.
 * Controlado: passe `state` (null = fechado) e os callbacks. O dialog só fecha
 * quando o pai zera o `state` (em `onConfirm`/`onCancel`).
 */
export default function ConfirmDialog({
  state,
  onConfirm,
  onCancel,
}: {
  state: ConfirmState | null;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const destrutivo = state?.destrutivo !== false;
  return (
    <AlertDialog open={!!state} onOpenChange={(open) => { if (!open) onCancel(); }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{state?.titulo}</AlertDialogTitle>
          {state?.descricao && (
            <AlertDialogDescription className="whitespace-pre-line">
              {state.descricao}
            </AlertDialogDescription>
          )}
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel}>
            {state?.cancelLabel ?? "Voltar"}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={(e) => { e.preventDefault(); onConfirm(); }}
            disabled={state?.carregando}
            className={destrutivo ? undefined : "bg-primary hover:bg-primary-600 text-on-primary focus:ring-primary"}
          >
            {state?.confirmLabel ?? "Confirmar"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

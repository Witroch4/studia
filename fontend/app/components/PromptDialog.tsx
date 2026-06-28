"use client";
import { useState } from "react";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from "@/components/ui/alert-dialog";

interface Props {
  open: boolean;
  titulo: string;
  descricao?: string;
  placeholder?: string;
  onConfirm: (valor: string) => void;
  onCancel: () => void;
}

/**
 * Dialog de input controlado — substitui window.prompt().
 * O `key` no pai (passado como `open ? cadernoId : "closed"`) garante
 * que o estado interno é resetado ao abrir um novo dialog.
 */
export function PromptDialog({ open, titulo, descricao, placeholder, onConfirm, onCancel }: Props) {
  const [valor, setValor] = useState("");
  return (
    <AlertDialog open={open} onOpenChange={(o) => { if (!o) onCancel(); }}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{titulo}</AlertDialogTitle>
          {descricao ? <AlertDialogDescription>{descricao}</AlertDialogDescription> : null}
        </AlertDialogHeader>
        <input
          autoFocus
          value={valor}
          placeholder={placeholder}
          onChange={(e) => setValor(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && valor.trim()) onConfirm(valor.trim()); }}
          className="w-full rounded-md border border-border bg-surface px-3 py-2 text-sm text-fg outline-none focus:border-primary"
        />
        <AlertDialogFooter>
          <AlertDialogCancel onClick={onCancel}>Cancelar</AlertDialogCancel>
          <AlertDialogAction
            disabled={!valor.trim()}
            onClick={() => onConfirm(valor.trim())}
            className="bg-primary hover:bg-primary/90 text-on-primary focus:ring-primary"
          >
            Confirmar
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}

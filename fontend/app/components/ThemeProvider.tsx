"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ComponentProps } from "react";

/**
 * Gestor de tema do studIA (claro/escuro).
 *
 * - attribute="class": next-themes alterna a classe `.dark` no <html>.
 * - defaultTheme="dark": o padrão do app é o dark atual; claro é opt-in.
 * - enableSystem={false}: NÃO seguimos o tema do SO — só o que o usuário escolher.
 * - O provider injeta um script bloqueante no <head> que aplica a classe ANTES
 *   da primeira pintura → sem flash branco e sem mismatch de hidratação
 *   (o <html> usa suppressHydrationWarning no layout).
 */
export function ThemeProvider({ children, ...props }: ComponentProps<typeof NextThemesProvider>) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="dark"
      enableSystem={false}
      disableTransitionOnChange
      storageKey="studia-theme"
      {...props}
    >
      {children}
    </NextThemesProvider>
  );
}

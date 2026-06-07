import type { Metadata } from "next";
import "katex/dist/katex.min.css";
import "./globals.css";
import AppShell from "./components/AppShell";

export const metadata: Metadata = {
  title: "studIA - Dashboard",
  description: "Plataforma de estudos inteligente",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="pt-BR" className="dark">
      <head>
        <link
          href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap"
          rel="stylesheet"
        />
        <link
          href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-bg-dark text-text-dark min-h-screen flex antialiased">
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}

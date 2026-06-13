import type { Metadata } from "next";
import PainelClient from "./PainelClient";

export const metadata: Metadata = {
  title: "Painel",
  description: "Seu painel de estudos: horas, precisão, disciplinas e constância.",
  robots: { index: false, follow: false },
};

export default function Painel() {
  return <PainelClient />;
}

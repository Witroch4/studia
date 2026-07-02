import PerfilPublicoClient from "./PerfilPublicoClient";

export default async function PerfilPublicoPage({
  params,
}: {
  params: Promise<{ apelido: string }>;
}) {
  const { apelido } = await params;
  return <PerfilPublicoClient apelido={apelido} />;
}

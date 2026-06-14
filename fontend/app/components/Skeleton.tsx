/** Bloco de carregamento. Usar SÓ no load inicial (isPending), nunca em refetch/mutation. */
export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`animate-pulse bg-surface-2 rounded ${className}`} />;
}

import { QueryClient } from "@tanstack/react-query";

/** Factory do QueryClient. Defaults conservadores p/ app single-user. */
export function makeQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: {
        staleTime: 30_000, // 30s "fresco" — evita refetch redundante ao navegar
        gcTime: 5 * 60_000, // 5min em cache após inativo
        retry: 1,
        refetchOnWindowFocus: false,
      },
    },
  });
}

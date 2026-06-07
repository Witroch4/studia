import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Permite buildar num diretório separado (ex.: verificar build sem brigar
  // com o .next do dev server). Default continua ".next".
  distDir: process.env.NEXT_DIST_DIR || ".next",
  // better-auth/kysely-adapter/pg ficam fora do bundle do servidor:
  //  - evita o build pesado (todos os adapters) → OOM
  //  - o webpack tolera os imports condicionais sqlite/d1 do kysely-adapter
  // O componente que usa useSession é carregado só no cliente (ssr:false),
  // então o better-auth/react nunca roda no prerender (sem React duplicado).
  serverExternalPackages: ["better-auth", "@better-auth/kysely-adapter", "kysely", "pg"],
};

export default nextConfig;

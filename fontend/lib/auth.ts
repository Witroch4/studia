import { betterAuth } from "better-auth";
import { admin } from "better-auth/plugins/admin";
import { nextCookies } from "better-auth/next-js";
import { Pool } from "pg";

/**
 * Better Auth server — studIA (single-tenant).
 *
 * Estratégia de sessão: dados da sessão ficam assinados num cookie
 * (`session.cookieCache`), então o app NÃO bate no Postgres a cada request —
 * só relê do banco quando o cache expira (5 min) ou a sessão é renovada.
 * As tabelas (user/session/account/verification) vivem no mesmo Postgres do
 * studIA. Roles via plugin `admin` (campo `role`: "admin" | "user").
 */

const DEFAULT_DEV_SECRET = "studia-dev-better-auth-secret-change-in-prod-0001";

// node-pg precisa de uma URL sem o sufixo "+asyncpg" usado pelo backend Python.
const databaseUrl = (
  process.env.AUTH_DATABASE_URL ||
  process.env.DATABASE_URL ||
  "postgresql://postgres:postgres@localhost:5432/studia"
).replace("+asyncpg", "");

export const auth = betterAuth({
  baseURL: process.env.BETTER_AUTH_URL || "http://localhost:3000",
  secret: process.env.BETTER_AUTH_SECRET || DEFAULT_DEV_SECRET,
  database: new Pool({ connectionString: databaseUrl }),

  emailAndPassword: {
    enabled: true,
    // App pessoal: só o admin cria usuários (via seed / painel /conta). Sem signup público.
    disableSignUp: true,
    minPasswordLength: 4,
  },

  session: {
    expiresIn: 60 * 60 * 24 * 30, // 30 dias
    updateAge: 60 * 60 * 24, // renova a cada 1 dia de uso
    cookieCache: {
      enabled: true,
      maxAge: 5 * 60, // 5 min de sessão no cookie antes de revalidar no banco
    },
  },

  user: {
    additionalFields: {
      role: { type: "string", required: false, defaultValue: "user", input: false },
    },
  },

  plugins: [
    admin({ defaultRole: "user", adminRoles: ["admin"] }),
    nextCookies(), // mantém set-cookie em server actions — deve ser o último
  ],
});

export type Session = typeof auth.$Infer.Session;

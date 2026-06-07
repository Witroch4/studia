/**
 * Seed do usuário admin do studIA.
 * Usa a API interna do Better Auth (mesmo hashing do runtime), então funciona
 * mesmo com signup público desabilitado.
 *
 *   pnpm dlx tsx scripts/seed-admin.ts
 *
 * Variáveis (com defaults): SEED_EMAIL, SEED_PASSWORD, SEED_NAME, SEED_ROLE
 */
import { auth } from "../lib/auth";

const email = process.env.SEED_EMAIL || "witalo_rocha@hotmail.com";
const password = process.env.SEED_PASSWORD || "2357@";
const name = process.env.SEED_NAME || "Witalo Rocha";
const role = process.env.SEED_ROLE || "admin";

async function main() {
  const ctx = await auth.$context;

  const existing = await ctx.internalAdapter.findUserByEmail(email);
  if (existing?.user) {
    // garante role admin + email verificado mesmo se já existia
    await ctx.internalAdapter.updateUser(existing.user.id, { role, emailVerified: true });
    console.log(`✓ usuário já existia — atualizado para role=${role}: ${email}`);
    process.exit(0);
  }

  const user = await ctx.internalAdapter.createUser({
    email,
    name,
    emailVerified: true,
    role,
  } as never);

  const hash = await ctx.password.hash(password);
  await ctx.internalAdapter.createAccount({
    userId: user.id,
    providerId: "credential",
    accountId: user.id,
    password: hash,
  } as never);

  console.log(`✓ admin criado: ${email} (id=${user.id}, role=${role})`);
  process.exit(0);
}

main().catch((err) => {
  console.error("✗ falha no seed:", err);
  process.exit(1);
});

"use client";

import { createAuthClient } from "better-auth/react";
import { adminClient } from "better-auth/client/plugins";

/**
 * Better Auth client — usado pelos componentes ("use client").
 * baseURL vazio = mesma origem do Next.js (rota /api/auth).
 */
export const authClient = createAuthClient({
  plugins: [adminClient()],
});

export const { signIn, signOut, signUp, useSession } = authClient;

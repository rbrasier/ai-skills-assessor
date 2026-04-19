/**
 * @ai-skills-assessor/database
 *
 * Re-exports the generated Prisma client and exposes a singleton instance for
 * application code. Run `pnpm --filter @ai-skills-assessor/database generate`
 * before importing types from this package.
 */

import { PrismaClient } from "./generated/client/index.js";

export * from "./generated/client/index.js";

declare global {
  // eslint-disable-next-line no-var
  var __aiSkillsAssessorPrisma: PrismaClient | undefined;
}

/**
 * A process-wide singleton Prisma client. Reusing one client across hot
 * reloads (e.g. in Next.js dev mode) prevents connection pool exhaustion.
 */
export const prisma: PrismaClient =
  globalThis.__aiSkillsAssessorPrisma ?? new PrismaClient();

if (process.env.NODE_ENV !== "production") {
  globalThis.__aiSkillsAssessorPrisma = prisma;
}

/**
 * Database seed script.
 *
 * Phase 1 ships an empty seed; later phases will populate SFIA reference data
 * and demo candidates / sessions for local development.
 */

async function main(): Promise<void> {
  // eslint-disable-next-line no-console
  console.log("[seed] Phase 1 seed is intentionally empty.");
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error("[seed] failed:", err);
  process.exit(1);
});

import { defineRailway, github, preserve, project, service, volume } from "railway/iac";

export default defineRailway(() => {
  // SQLite lives here. Without a volume a redeploy wipes the whole history.
  const familyBudgetVolume = volume("family-budget-volume", {
    alerts: { usage: { "80": {}, "95": {}, "100": {} } },
    allowOnlineResize: true,
    region: "iad",
    sizeMB: 500,
  });

  const familyBudget = service("family-budget", {
    // rootDirectory is what makes Railway build tg-bot/Dockerfile. Without it
    // the builder sees the repo root, finds no Dockerfile, falls back to
    // Railpack and fails on a repo that has no app at the top level.
    source: github("serhii-skotarenko/family-budget", {
      upstreamUrl: "https://github.com/serhii-skotarenko/family-budget",
      rootDirectory: "tg-bot",
    }),

    // Long polling: a second replica would fight the first over getUpdates.
    // Railway also forbids replicas on a service with a volume.
    replicas: { iad: 1 },

    volumeMounts: { "/data": familyBudgetVolume },

    // Values stay in Railway, not in this file. DATABASE_PATH is deliberately
    // absent: the image points it at the mounted volume, and overriding it
    // moves the database onto the container filesystem, losing it on redeploy.
    env: {
      TELEGRAM_BOT_TOKEN: preserve(),
      ALLOWED_TELEGRAM_IDS: preserve(),
      HOUSEHOLD_NAME: preserve(),
    },
  });

  return project("fbdgt-trckr-bot", {
    resources: [familyBudget, familyBudgetVolume],
  });
});

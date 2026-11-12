import { mkdirSync } from "node:fs";
import { spawnSync } from "node:child_process";

mkdirSync("coverage", { recursive: true });
const result = spawnSync(process.execPath, [
  "--test",
  "--experimental-test-coverage",
  "--test-coverage-include=javascript/pricing.js",
  "--test-reporter=spec",
  "--test-reporter-destination=stdout",
  "--test-reporter=lcov",
  "--test-reporter-destination=coverage/lcov.info",
  "javascript/pricing.test.js"
], { stdio: "inherit" });
if (result.error) {
  console.error(result.error.message);
  process.exitCode = 1;
} else {
  process.exitCode = result.status ?? 1;
}

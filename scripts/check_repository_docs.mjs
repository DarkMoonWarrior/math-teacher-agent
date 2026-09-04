// Read-only hygiene check for tracked Markdown and the retired UI boundary.
import { execFileSync } from "node:child_process";
import { existsSync, readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const tracked = execFileSync("git", ["ls-files", "-z"], { cwd: root, encoding: "utf8" })
  .split("\0").filter(Boolean);
const markdown = tracked.filter((path) => path.endsWith(".md") && existsSync(resolve(root, path)));
const errors = [];
let links = 0;
for (const path of markdown) {
  const content = readFileSync(resolve(root, path), "utf8");
  const archived = /^docs\/(commercial-v1|high-school-math-ai)\//.test(path);
  if (archived && !/归档|历史/.test(content)) errors.push(`${path}: missing archive context`);
  // Fenced examples are not navigation links.
  const prose = content.replace(/^```[^\n]*\n[\s\S]*?^```\s*$/gm, "");
  for (const match of prose.matchAll(/\[[^\]\n]*\]\(([^)\n]+)\)/g)) {
    const target = match[1].replace(/^<|>$/g, "").split(/\s+"/)[0];
    if (/^(?:[a-z][a-z\d+.-]*:|#|\/\/)/i.test(target)) continue;
    const local = decodeURIComponent(target.split(/[?#]/)[0]);
    if (!local) continue;
    links++;
    if (!existsSync(resolve(root, dirname(path), local))) errors.push(`${path}: missing link ${target}`);
  }
}
for (const path of ["package.json", "pnpm-lock.yaml", "pnpm-workspace.yaml"]) {
  if (/apps\/web|legacy-web|@math-ai\/web/.test(readFileSync(resolve(root, path), "utf8"))) {
    errors.push(`${path}: retired UI dependency or command`);
  }
}
if (existsSync(resolve(root, "apps/web"))) errors.push("Retired apps/web directory still exists");
if (errors.length) {
  console.error(errors.join("\n"));
  process.exitCode = 1;
} else {
  console.log(`Checked ${markdown.length} tracked Markdown files and ${links} local links; retired UI boundary clean.`);
}

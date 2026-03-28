import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import ts from "typescript";
import { pathToFileURL } from "node:url";

const root = path.resolve(process.cwd(), "frontend");
const sourcePath = path.join(root, "src", "nameResolver.ts");
const tempDir = path.join(root, ".tmp-check");
const tempPath = path.join(tempDir, "nameResolver.check.mjs");

if (!fs.existsSync(sourcePath)) {
  throw new Error(`Missing source module: ${sourcePath}`);
}

fs.mkdirSync(tempDir, { recursive: true });

const source = fs.readFileSync(sourcePath, "utf8");
const output = ts.transpileModule(source, {
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2020,
  },
  fileName: sourcePath,
}).outputText;

fs.writeFileSync(tempPath, output, "utf8");

const mod = await import(pathToFileURL(tempPath).href + `?t=${Date.now()}`);

const catalog = mod.buildNameCatalog([
  { id: "Ball Lightning", name: "球状闪电", displayName: "球状闪电" },
  { id: "BootSequence", name: "启动流程", displayName: "启动流程" },
  { id: "Ring of the Snake", name: "蛇之戒指", displayName: "蛇之戒指" },
]);

assert.equal(mod.resolveCatalogName("Ball Lightning", catalog), "球状闪电");
assert.equal(mod.resolveCatalogName("BootSequence", catalog), "启动流程");
assert.equal(mod.resolveCatalogName("Ring of the Snake", catalog), "蛇之戒指");
assert.equal(
  mod.resolveKnownName("Ring of the Snake", "铔囦箣鎴掓寚", mod.RELIC_NAME_OVERRIDES),
  "蛇之戒指",
);
assert.equal(
  mod.resolveKnownName("Unknown_Card", null, mod.CARD_NAME_OVERRIDES),
  "Unknown Card",
);

console.log("name resolver checks passed");

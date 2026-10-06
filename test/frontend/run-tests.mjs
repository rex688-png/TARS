import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const requireFromUi = createRequire(new URL("../../ui/package.json", import.meta.url));
const { build } = requireFromUi("esbuild");

const result = await build({
  entryPoints: [fileURLToPath(new URL("./tars-frontend-foundation.test.ts", import.meta.url))],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  write: false,
  sourcemap: "inline",
});

const source = result.outputFiles[0].text;
await import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);

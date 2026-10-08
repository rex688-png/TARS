import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import path from "node:path";

const requireFromUi = createRequire(new URL("../../ui/package.json", import.meta.url));
const { build } = requireFromUi("esbuild");

const result = await build({
  entryPoints: [
    fileURLToPath(new URL("./tars-frontend-foundation.test.ts", import.meta.url)),
    fileURLToPath(new URL("./tars-native-shell.test.ts", import.meta.url)),
  ],
  bundle: true,
  format: "esm",
  platform: "node",
  target: "node20",
  outdir: path.join(tmpdir(), "tars-frontend-tests"),
  write: false,
  sourcemap: "inline",
});

for (const output of result.outputFiles) {
  await import(`data:text/javascript;base64,${Buffer.from(output.text).toString("base64")}`);
}

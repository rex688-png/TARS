import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';
import { resolveAppUiAssetPath } from '../../electron/app-ui-assets.js';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../../ui/src');

test('packaged app protocol resolves the original TARS avatar with spaces', () => {
  const filename = 'Obraz ChatGPT 28 wrz 2026, 21_39_52.png';
  const asset = resolveAppUiAssetPath(root, `app://./assets/${encodeURIComponent(filename)}`);
  assert.equal(path.basename(asset), filename);
  assert.equal(readFileSync(asset).subarray(1, 4).toString(), 'PNG');
});

test('packaged app protocol keeps asset requests inside the UI bundle', () => {
  assert.equal(resolveAppUiAssetPath(root, 'app://./assets/%2E%2E%2F%2E%2E%2Fprivate.txt'), null);
  assert.equal(resolveAppUiAssetPath(root, 'app://./assets/%ZZ.png'), null);
  assert.equal(resolveAppUiAssetPath(root, 'app://./'), path.join(root, 'index.html'));
});

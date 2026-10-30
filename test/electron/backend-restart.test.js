import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';

// Execute the production class, without starting Electron or real backend processes.
function harness(overrides = {}) {
  const source = fs.readFileSync(new URL('../../electron/index.js', import.meta.url), 'utf8');
  const children = [], messages = [];
  const window = new EventEmitter();
  window.webContents = { send: (...args) => messages.push(args) };
  const context = {
    logger: { info() {}, warn() {}, error() {} },
    app: new EventEmitter(), config: {}, process: { env: {} },
    tarsRuntimeProfile: false, tarsApplicationPaths: null,
    buildBackendEnvironment: () => ({}), shouldRedactConfigLine: () => false,
    isBlackBoxLine: () => false, setTimeout, clearTimeout,
    spawn() {
      const child = new EventEmitter();
      Object.assign(child, { pid: children.length + 1, exitCode: null, signalCode: null, kills: [] });
      child.kill = signal => child.kills.push(signal);
      for (const name of ['stdin', 'stdout', 'stderr']) {
        child[name] = new EventEmitter();
        child[name].setEncoding = () => {};
      }
      children.push(child);
      return child;
    },
    ...overrides,
  };
  const klass = source.slice(source.indexOf('class BackendService {'), source.indexOf('\n\nfunction createMainWindow()'));
  const BackendService = vm.runInNewContext(`${klass}\nBackendService`, context);
  return { backend: new BackendService(), window, children, messages };
}

test('restart waits for old backend close; concurrent starts share one replacement', async () => {
  const h = harness();
  await h.backend.startProcess(h.window);
  const restart = h.backend.startProcess(h.window);
  const duplicate = h.backend.startProcess(h.window);
  assert.equal(h.children.length, 1, 'old backend still owns the database/devices');
  assert.equal(h.children[0].kills.length, 1);
  h.children[0].emit('close', 0, null);
  await Promise.all([restart, duplicate]);
  assert.equal(h.children.length, 2);
});

test('repeated starts do not multiply window subscriptions or deliveries', async () => {
  const h = harness();
  await h.backend.startProcess(h.window);
  for (let n = 0; n < 15; n++) {
    h.children.at(-1).exitCode = 0;
    h.children.at(-1).emit('close', 0, null);
    await h.backend.startProcess(h.window);
  }
  assert.equal(h.window.listenerCount('close'), 1);
  h.messages.length = 0;
  h.children.at(-1).stdout.emit('data', 'one notification\n');
  assert.equal(h.messages.length, 1);
});

test('closed window cancels a pending replacement', async () => {
  const h = harness();
  await h.backend.startProcess(h.window);
  const restart = h.backend.startProcess(h.window);
  h.window.emit('close');
  h.children[0].emit('close', 0, null);
  await restart;
  assert.equal(h.children.length, 1);
});

test('restart timeout fails closed and removes its wait listener', async () => {
  let expire;
  const h = harness({ setTimeout: callback => { expire = callback; return 1; }, clearTimeout() {} });
  await h.backend.startProcess(h.window);
  const restart = h.backend.startProcess(h.window);
  expire();
  await assert.rejects(restart, /restart cancelled/);
  assert.equal(h.children.length, 1);
  assert.equal(h.children[0].listenerCount('close'), 1);
  h.children[0].emit('close', 0, null);
  await h.backend.startProcess(h.window);
  assert.equal(h.children.length, 2);
});

test('stdin failure does not forget a still-live backend during restart', async () => {
  const h = harness();
  await h.backend.startProcess(h.window);
  h.children[0].stdin.writable = true;
  h.children[0].stdin.write = () => { throw new Error('pipe failed'); };
  assert.throws(() => h.backend.sendJsonLine({}, { jsonLine: '{}' }), /no longer accepting/);
  const restart = h.backend.startProcess(h.window);
  assert.equal(h.children.length, 1);
  h.children[0].emit('close', 0, null);
  await restart;
  assert.equal(h.children.length, 2);
});

test('process error before close retains ownership and still permits later restart', async () => {
  const h = harness();
  await h.backend.startProcess(h.window);
  h.children[0].emit('error', new Error('synthetic process error'));
  const restart = h.backend.startProcess(h.window);
  assert.equal(h.children.length, 1);
  h.children[0].emit('close', 1, null);
  await restart;
  assert.equal(h.children.length, 2);
});

test('stop then start during an existing restart honors the latest start', async () => {
  const h = harness();
  await h.backend.startProcess(h.window);
  const first = h.backend.startProcess(h.window);
  h.backend.stopProcess(h.window);
  const latest = h.backend.startProcess(h.window);
  h.children[0].emit('close', 0, null);
  await Promise.all([first, latest]);
  assert.equal(h.children.length, 2);
});

import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

import {
  TARS_APP_ID,
  TARS_PRODUCT_NAME,
  buildBackendEnvironment,
  configureTarsApplication,
  resolveTarsApplicationPaths,
} from '../../electron/tars-runtime-profile.js';

test('uses an isolated TARS application identity', () => {
  assert.equal(TARS_PRODUCT_NAME, 'TARS');
  assert.equal(TARS_APP_ID, 'com.rex688.tars');
});

test('packaged application metadata uses the TARS identity', () => {
  const packageJson = JSON.parse(
    fs.readFileSync(new URL('../../package.json', import.meta.url), 'utf8'),
  );
  assert.equal(packageJson.build.productName, TARS_PRODUCT_NAME);
  assert.equal(packageJson.build.appId, TARS_APP_ID);
});

test('packaged path configuration precedes logger initialization', () => {
  const source = fs.readFileSync(
    new URL('../../electron/index.js', import.meta.url),
    'utf8',
  );
  const configureCall = source.indexOf('configureTarsApplication(app)');
  const loggerConfiguration = source.indexOf('const transport =');
  assert.ok(configureCall >= 0);
  assert.ok(loggerConfiguration > configureCall);
});

test('resolves user data, session data, and logs under AppData/TARS', () => {
  const paths = resolveTarsApplicationPaths(path.join('C:', 'Users', 'TEST', 'AppData', 'Roaming'));
  assert.equal(paths.userData, path.join('C:', 'Users', 'TEST', 'AppData', 'Roaming', 'TARS'));
  assert.equal(paths.sessionData, path.join(paths.userData, 'session'));
  assert.equal(paths.logs, path.join(paths.userData, 'logs'));
  assert.equal(paths.userData.includes('com.covas-next.ui'), false);
});

test('configures paths before consumers request them', () => {
  const calls = [];
  const fakeApp = {
    getPath: name => {
      assert.equal(name, 'appData');
      return '/test/roaming';
    },
    setName: name => calls.push(['name', name]),
    setPath: (name, value) => calls.push(['path', name, value]),
    setAppLogsPath: value => calls.push(['logs', value]),
  };

  const paths = configureTarsApplication(fakeApp);
  assert.deepEqual(calls, [
    ['name', 'TARS'],
    ['path', 'userData', paths.userData],
    ['path', 'sessionData', paths.sessionData],
    ['logs', paths.logs],
  ]);
});

test('enables the internal profile only for the packaged backend', () => {
  assert.deepEqual(buildBackendEnvironment({ EXISTING: 'kept' }, true), {
    EXISTING: 'kept',
    TARS_RUNTIME_PROFILE: '1',
  });
  assert.deepEqual(buildBackendEnvironment({ EXISTING: 'kept' }, false), {
    EXISTING: 'kept',
  });
});

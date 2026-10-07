import path from 'node:path';

export const TARS_PRODUCT_NAME = 'TARS';
export const TARS_APP_ID = 'com.rex688.tars';

export function resolveTarsApplicationPaths(appDataPath) {
  const userData = path.join(appDataPath, TARS_PRODUCT_NAME);
  return {
    userData,
    sessionData: path.join(userData, 'session'),
    logs: path.join(userData, 'logs'),
  };
}

export function configureTarsApplication(app) {
  const paths = resolveTarsApplicationPaths(app.getPath('appData'));
  app.setName(TARS_PRODUCT_NAME);
  app.setPath('userData', paths.userData);
  app.setPath('sessionData', paths.sessionData);
  app.setAppLogsPath(paths.logs);
  return paths;
}

export function buildBackendEnvironment(
  baseEnvironment,
  enabled,
  resourcesPath = undefined,
  userDataPath = undefined,
) {
  return enabled
    ? {
        ...baseEnvironment,
        TARS_RUNTIME_PROFILE: '1',
        ...(resourcesPath
          ? { TARS_BUNDLED_RESOURCES: path.join(resourcesPath, 'tars-plugins') }
          : {}),
        ...(userDataPath
          ? { TARS_PROVIDER_ROOT: path.join(userDataPath, 'providers') }
          : {}),
      }
    : { ...baseEnvironment };
}

import path from 'node:path';

/** Resolve packaged app:// UI assets, including filenames with spaces. */
export function resolveAppUiAssetPath(uiDirectory, requestUrl) {
  let pathname;
  try {
    pathname = decodeURIComponent(new URL(requestUrl).pathname);
  } catch {
    return null;
  }
  const root = path.resolve(uiDirectory);
  const filePath = path.resolve(root, `.${pathname === '/' ? '/index.html' : pathname}`);
  if (filePath !== root && !filePath.startsWith(root + path.sep)) return null;
  return filePath;
}

# TARS Angular frontend

This Angular application is the renderer for the Windows Electron shell. From
the repository root, install dependencies with `npm ci` and `npm ci --prefix ui`.
Use `npm run test:frontend-foundation` for focused frontend tests and
`npm run build:ui` for the production renderer bundle. Electron packages the UI
from `ui/dist/covas-next-ui/browser`; that directory is a retained build
identifier, not the product name.

The frontend talks to the existing Python runtime through Electron and the
established message services. See [project installation and runtime notes](../docs/tars-installation.md).

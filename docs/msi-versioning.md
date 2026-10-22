# MSI version ordering and disposable Windows acceptance

Root `package.json` remains the human-readable SemVer authority. Versions in both
manifests and the lockfile stay **0.0.0** in this sprint. No tag or release is
created. The supported build-time policy is implemented once in
`tools/msi-version.cjs`; the MSI hook and release validation/provenance use it.

## Verified installer foundation

The lockfile resolves Electron Builder/app-builder-lib **26.8.1** and Electron
38.8.6. MsiTarget passes `AppInfo.getVersionInWeirdWindowsForm()` to its WiX
Product Version. That function uses parseInt on the first three SemVer components
and appends a numeric build number or zero. Thus beta.1 and beta.2 of 0.5.0 both
become 0.5.0.0. Windows Installer compares only major/minor/build (limits
255/255/65535); an incremented fourth component does not fix the collision.
See Microsoft's [ProductVersion semantics](https://learn.microsoft.com/windows/win32/msi/productversion).

The existing template uses Product Id="*" (a new ProductCode per MSI build), and
MajorUpgrade AllowSameVersionUpgrades="yes", with a newer-version launch error.
UpgradeCode is UUID v5 of com.rex688.tars under the builder namespace
`d752fe43-5d44-44d5-9fc9-6dd1bf19d5cc`:
**AC5C2268-982F-5911-BC2F-9D5E9DFDCDF9**. The hook checks, but does not replace,
that identity. Package/app IDs, installer scope defaults, shortcuts and
%APPDATA%\TARS remain unchanged. No node_modules patch or custom installer
rewrite is used: the supported msiProjectCreated hook changes only ProductVersion.

With the same UpgradeCode and installation context, FindRelatedProducts and the
Upgrade table identify the previous product; RemoveExistingProducts removes it.
The existing same-version inclusive relationship replaces a different ProductCode
at the same version rather than installing a duplicate. Installing the identical
cached ProductCode takes the MSI maintenance path. A higher installed version
sets WIX_DOWNGRADE_DETECTED and the existing LaunchCondition rejects the install.
Same-version rebuilding is an intentional reinstall, not a new release version.
CI tests these mechanisms rather than relying only on template comments.

## Bounded, monotonic mapping

Use `major.minor.(patch * 256 + rank)`, where beta.N has rank N (1..254) and
stable has rank 255. Each major/minor/patch component must be 0..255. Other
prerelease channels, build metadata, beta 0/255+, patch 256+, and overflow are
rejected, never truncated, wrapped or silently aliased. The limits reserve one
byte for each semantic patch and one for the channel/rank inside MSI's 16-bit
third component. This is a documented supported version space, not a promise to
encode unlimited SemVer in finite Windows fields. A future need to exceed it
requires an explicit policy review, not a fallback to colliding versions.

| Human version | MSI ProductVersion |
| --- | --- |
| 0.0.0 (reserved legacy placeholder) | 0.0.0.0, unchanged |
| 0.5.0-beta.1 | 0.5.1 |
| 0.5.0-beta.2 | 0.5.2 |
| 0.5.0-beta.254 | 0.5.254 |
| 0.5.0 | 0.5.255 |
| 0.5.1-beta.1 | 0.5.257 |
| 0.5.1 | 0.5.511 |
| 0.6.0-beta.1 | 0.6.1 |

0.0.0 is reserved only for the existing unreleased package; 0.0.0-beta.N is
rejected. Official v0.0.0 remains forbidden. Within the accepted space, distinct
versions cannot collide and numeric order matches beta-to-stable and subsequent
patch/minor/major order. Reassigning the same semantic version to different
release content is still forbidden by review/tag/asset safeguards; MSI explicitly
allows a same-version reinstall. There is no independent counter or version ledger.

Alternatives rejected: a fourth numeric component is ignored for ordering;
using N alone as the patch collides with future semantic patch releases;
a sequential CI run number makes stable ordering depend on build history and
adds a second version authority; an installer-template/identity rewrite is not
needed because the locked builder exposes a narrow pre-compilation hook.

## Evidence required from Windows CI

`e2e/MsiMetadata.ps1` reads actual MSI Property, Upgrade, LaunchCondition and
InstallExecuteSequence tables through Windows Installer COM. The normal packaging
job validates the actual full TARS MSI against this mapping and unchanged
UpgradeCode, including the current 0.0.0 package. Its notice records ProductVersion,
ProductCode and UpgradeCode. Release provenance includes the mapped MSI version
and expected identity after that check.

The separate `MSI upgrade acceptance` job runs only on a disposable GitHub-hosted
Windows runner. It builds five real MSIs using the locked builder, the current
TARS identity and existing installer rules. Their tiny inert payload is Windows
where.exe renamed TARS.exe; it does not launch TARS or emulate its runtime.
The legacy fixture omits the new hook, reproducing the original 0.0.0.0 installer.
Other fixtures use isolated project metadata (beta.1, beta.2, stable and a rebuilt
stable), not changed production package versions.

The job refuses an existing TARS installation/profile, seeds a synthetic
%APPDATA%\TARS profile with personality/plugin/provider config, a real SQLite
memory marker, config backup and provider file, and checks hashes after each
operation. It performs real unattended msiexec installs in order: legacy -> beta.1
-> beta.2 -> stable; reinstalls the identical MSI; installs rebuilt stable with a
new ProductCode; then attempts and requires explicit rejection of beta.2. It
checks that exactly one related product remains installed and the old ProductCode
is removed. It uninstalls its fixture in a finally block. No owner profile,
credentials, journals, game files or model downloads are used.

Only the synthetic metadata/scenario report is uploaded, not these fixture MSIs
or user data. `acceptance-report.json` records actual ProductVersion/ProductCode/
UpgradeCode, upgrade table bounds/attributes, execution results and preserved
profile status. Absence/failure of real installation evidence must be reported
as a limitation; unit tests alone never certify an upgrade. The future draft
release job depends on this acceptance job as well as existing packaging/E2E.

## Approval boundaries

Even a successful disposable-runner test is not universal Windows acceptance.
It tests same-user default installation context and installer machinery with an
inert payload. It does not certify every historical machine-wide/per-user scope,
custom installation path, permissions, running app/file lock, reboot, endpoint
security policy or cross-user upgrade. Physical Windows 11 full-MSI installation
and upgrade with the owner's backed-up profile, TARS launch, audio, providers,
memory, vision and live Elite behavior remain required.

A later separately approved version assignment may use this policy only after
reviewing both the real fixture report and full-production-MSI metadata/CI.
No beta is assigned/published by this sprint. See [release approval](release-readiness.md).

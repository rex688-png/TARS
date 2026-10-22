/* Build-time MSI policy only; root package.json remains the SemVer authority. */
const fs = require('node:fs');
const path = require('node:path');
const UPGRADE_CODE = 'AC5C2268-982F-5911-BC2F-9D5E9DFDCDF9';

function productVersion(version) {
  const match = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-beta\.([1-9]\d*))?$/.exec(version);
  if (!match) throw new Error('MSI supports MAJOR.MINOR.PATCH[-beta.N] only');
  const [, major, minor, patch, beta] = match;
  if ([major, minor, patch].some(value => Number(value) > 255) || (beta && Number(beta) > 254)) {
    throw new Error('MSI policy requires components 0..255 and beta numbers 1..254; never wrap or truncate');
  }
  if (+major === 0 && +minor === 0 && +patch === 0) {
    if (beta) throw new Error('0.0.0 is reserved for the legacy unreleased installer');
    return '0.0.0.0'; // Preserve the current installer byte-for-byte at this property.
  }
  return `${major}.${minor}.${Number(patch) * 256 + (beta ? Number(beta) : 255)}`;
}

function rewriteProject(projectFile, version) {
  const original = fs.readFileSync(projectFile, 'utf8');
  const product = original.match(/<Product\b[^>]*>/g);
  if (!product || product.length !== 1 || !product[0].includes('Id="*"')) throw new Error('Unexpected MSI Product template');
  const identity = /\bUpgradeCode="\{?([^"}]+)\}?"/.exec(product[0]);
  if (!identity || identity[1].toUpperCase() !== UPGRADE_CODE) throw new Error('MSI UpgradeCode continuity changed');
  const mapped = productVersion(version);
  const changed = product[0].replace(/\bVersion="[^"]+"/, `Version="${mapped}"`);
  if (changed === product[0] && !product[0].includes(`Version="${mapped}"`)) throw new Error('Missing MSI ProductVersion');
  fs.writeFileSync(projectFile, original.replace(product[0], changed));
}

function msiProjectCreated(projectFile) {
  const metadata = JSON.parse(fs.readFileSync(path.join(__dirname, '../package.json'), 'utf8'));
  if (metadata.build.appId !== 'com.rex688.tars') throw new Error('TARS app identity changed');
  rewriteProject(projectFile, metadata.version);
}
module.exports = msiProjectCreated;
Object.assign(module.exports, { productVersion, rewriteProject, UPGRADE_CODE });
if (require.main === module) {
  console.log(JSON.stringify({product_version: productVersion(process.argv[2]), upgrade_code: UPGRADE_CODE}));
}

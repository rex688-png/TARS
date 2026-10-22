const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {UUID} = require('builder-util-runtime');
const policy = require('../../tools/msi-version.cjs');
const {AppInfo} = require('app-builder-lib/out/appInfo');

function compare(left, right) {
  const a = left.split('.').slice(0,3).map(Number), b = right.split('.').slice(0,3).map(Number);
  for (let i=0;i<3;i++) if (a[i]!==b[i]) return Math.sign(a[i]-b[i]);
  return 0; // Windows Installer ignores the fourth component.
}
test('locked builder collision is reproduced, then corrected using three fields', () => {
  const info = version => new AppInfo({metadata:{name:'tars',version},config:{},devMetadata:{}});
  assert.equal(info('0.5.0-beta.1').getVersionInWeirdWindowsForm(), info('0.5.0-beta.2').getVersionInWeirdWindowsForm());
  assert.equal(compare('0.5.0.1','0.5.0.2'),0);
  const versions=['0.0.0','0.5.0-beta.1','0.5.0-beta.2','0.5.0'];
  assert.deepEqual(versions.map(policy.productVersion),['0.0.0.0','0.5.1','0.5.2','0.5.255']);
  for(let i=1;i<versions.length;i++) assert.equal(compare(policy.productVersion(versions[i-1]),policy.productVersion(versions[i])),-1);
  assert.equal(compare(policy.productVersion('0.5.0'),policy.productVersion('0.5.0')),0);
  assert.equal(compare(policy.productVersion('0.5.0'),policy.productVersion('0.5.0-beta.2')),1);
});
test('bounded version space is injective and monotonic across patch/minor/major boundaries', () => {
  const seen = new Set(); let previous;
  for (const major of [0,1,255]) for (const minor of [0,1,5,255]) for (const patch of [0,1,254,255]) {
    for (const suffix of ['-beta.1','-beta.2','-beta.254','']) {
      const version=`${major}.${minor}.${patch}${suffix}`;
      if(version.startsWith('0.0.0')) continue;
      const mapped=policy.productVersion(version); assert(!seen.has(mapped)); seen.add(mapped);
      if(previous) assert.equal(compare(previous,mapped),-1);
      previous=mapped;
      const fields=mapped.split('.').map(Number); assert(fields[0]<=255 && fields[1]<=255 && fields[2]<=65535);
    }
  }
});
test('overflow, unsupported prereleases and zero aliases fail closed', () => {
  for(const version of ['256.0.0','0.256.0','0.5.256','0.5.0-beta.255','0.5.0-beta.0','0.5.0-beta.01','0.5.0-rc.1','0.0.0-beta.1','0.5.0+build.2']) {
    assert.throws(()=>policy.productVersion(version), version);
  }
});
test('UpgradeCode equals the existing builder derivation, without a new identity setting', () => {
  assert.equal(policy.UPGRADE_CODE,UUID.v5('com.rex688.tars',UUID.parse('d752fe43-5d44-44d5-9fc9-6dd1bf19d5cc')).toUpperCase());
  const pkg=require('../../package.json'); assert.equal(pkg.build.appId,'com.rex688.tars');
  assert.equal(pkg.build.msiProjectCreated,'./tools/msi-version.cjs'); assert(!pkg.build.msi?.upgradeCode);
});
test('hook alters only ProductVersion and preserves same-version/downgrade rules', () => {
  const dir=fs.mkdtempSync(path.join(os.tmpdir(),'tars-msi-hook-'));
  try {
    const file=path.join(dir,'project.wxs');
    const original=`<Product Id="*" UpgradeCode="${policy.UPGRADE_CODE}" Version="0.5.0.0"><MajorUpgrade AllowSameVersionUpgrades="yes" DowngradeErrorMessage="newer"/></Product>`;
    fs.writeFileSync(file,original); policy.rewriteProject(file,'0.5.0-beta.2');
    assert.equal(fs.readFileSync(file,'utf8'),original.replace('Version="0.5.0.0"','Version="0.5.2"'));
    fs.writeFileSync(file,original.replace(policy.UPGRADE_CODE,'BAD-IDENTITY'));
    assert.throws(()=>policy.rewriteProject(file,'0.5.0-beta.2'));
  } finally {fs.rmSync(dir,{recursive:true,force:true});}
});

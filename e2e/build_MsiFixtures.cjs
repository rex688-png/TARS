/* Disposable CI installer fixtures: real locked MSI target, inert tiny payload. */
const fs = require('node:fs');
const path = require('node:path');
const {build, Platform, Arch} = require('electron-builder');
const root=path.resolve(__dirname,'..');
(async () => {
  if(process.platform!=='win32' || process.env.GITHUB_ACTIONS!=='true' || process.env.RUNNER_ENVIRONMENT!=='github-hosted') throw new Error('Disposable GitHub-hosted Windows runner required');
  const output=path.join(process.env.RUNNER_TEMP,'tars-msi-acceptance'); fs.mkdirSync(output);
  const payload=path.join(output,'payload');fs.mkdirSync(payload);
  fs.copyFileSync(path.join(process.env.SystemRoot,'System32/where.exe'),path.join(payload,'TARS.exe'));
  fs.writeFileSync(path.join(payload,'fixture.txt'),'Synthetic inert installer fixture; never a TARS release.');
  const source=JSON.parse(fs.readFileSync(path.join(root,'package.json'),'utf8'));
  const matrix=[];
  for(const [label,version,legacy] of [['legacy','0.0.0',true],['beta1','0.5.0-beta.1'],['beta2','0.5.0-beta.2'],['stable','0.5.0'],['stable-rebuilt','0.5.0']]) {
    const project=path.join(output,label);fs.mkdirSync(project);fs.mkdirSync(path.join(project,'tools'));
    fs.copyFileSync(path.join(root,'tools/msi-version.cjs'),path.join(project,'tools/msi-version.cjs'));
    const config={...source.build, directories:{buildResources:path.join(root,'electron'),output:path.join(project,'dist')},
      win:{...source.build.win,icon:path.join(root,'electron/icon.ico')},
      electronVersion:require('electron/package.json').version};
    if(legacy) delete config.msiProjectCreated;
    else config.msiProjectCreated=path.join(project,'tools/msi-version.cjs');
    fs.writeFileSync(path.join(project,'package.json'),JSON.stringify({...source,version,build:config},null,2));
    const artifacts=await build({projectDir:project, prepackaged:payload, targets:Platform.WINDOWS.createTarget('msi',Arch.x64),publish:'never'});
    const msi=artifacts.find(name=>name.endsWith('.msi'));if(!msi)throw new Error('MSI fixture missing');
    matrix.push({label,version,msi});
  }
  fs.writeFileSync(path.join(output,'matrix.json'),JSON.stringify(matrix,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});

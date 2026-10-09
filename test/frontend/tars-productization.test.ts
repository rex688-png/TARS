import assert from 'node:assert/strict';
import { test } from 'node:test';
import { needsSetup, setupFinishProblem } from '../../ui/src/app/services/tars-setup-state';
import { tarsActivityStatus } from '../../ui/src/app/main-view/tars-status';

test('new and incomplete profiles enter resumable setup; valid upgrades remain in shell',()=>{
 assert.equal(needsSetup({}),true);
 assert.equal(needsSetup({commander_name:'TEST',llm_provider:'openai',llm_api_key:''}),true);
 assert.equal(needsSetup({commander_name:'TEST',llm_provider:'openai',llm_api_key:'placeholder'}),false);
 assert.equal(needsSetup({commander_name:'TEST',llm_provider:'openai',tars_setup_step:4}),true);
 assert.equal(needsSetup({commander_name:'TEST',llm_provider:'openai',tars_setup_complete:true}),false);
});

test('setup completion rejects incomplete or unavailable AI without resetting saved progress',()=>{
 assert.match(setupFinishProblem({tars_setup_step:7},[] )??'',/commander/);
 assert.match(setupFinishProblem({commander_name:'TEST',llm_provider:'openai',tars_setup_step:7},[] )??'',/API key/);
 assert.match(setupFinishProblem({commander_name:'TEST',llm_provider:'plugin:missing:provider',tars_setup_step:7},[] )??'',/available AI provider/);
 assert.equal(setupFinishProblem({commander_name:'TEST',llm_provider:'openai',api_key:'placeholder',tars_setup_step:7},[]),null);
 const installed=[{kind:'llm' as const,id:'approved',plugin_guid:'guid',label:'Approved',is_builtin:false,settings_config:[]}];
 assert.equal(setupFinishProblem({commander_name:'TEST',llm_provider:'plugin:guid:approved',tars_setup_step:7},installed),null);
});

test('spoken activity uses readable state labels even when thinking is derived',()=>{
 assert.equal(tarsActivityStatus('running','idle'),'READY');
 assert.equal(tarsActivityStatus('running','listening'),'LISTENING');
 assert.equal(tarsActivityStatus('running','thinking'),'THINKING');
 assert.equal(tarsActivityStatus('running','speaking'),'SPEAKING');
 assert.equal(tarsActivityStatus('configuring','idle'),'OFFLINE');
});

import assert from 'node:assert/strict';
import { test } from 'node:test';
import { needsSetup } from '../../ui/src/app/services/tars-setup-state';
import { tarsActivityStatus } from '../../ui/src/app/main-view/tars-status';

test('new and incomplete profiles enter resumable setup; valid upgrades remain in shell',()=>{
 assert.equal(needsSetup({}),true);
 assert.equal(needsSetup({commander_name:'TEST',llm_provider:'openai',llm_api_key:''}),true);
 assert.equal(needsSetup({commander_name:'TEST',llm_provider:'openai',llm_api_key:'placeholder'}),false);
 assert.equal(needsSetup({commander_name:'TEST',llm_provider:'openai',tars_setup_step:4}),true);
 assert.equal(needsSetup({commander_name:'TEST',llm_provider:'openai',tars_setup_complete:true}),false);
});

test('spoken activity uses readable state labels even when thinking is derived',()=>{
 assert.equal(tarsActivityStatus('running','idle'),'READY');
 assert.equal(tarsActivityStatus('running','listening'),'LISTENING');
 assert.equal(tarsActivityStatus('running','thinking'),'THINKING');
 assert.equal(tarsActivityStatus('running','speaking'),'SPEAKING');
 assert.equal(tarsActivityStatus('configuring','idle'),'OFFLINE');
});

"""Opt-in deterministic control through existing ActionManager permissions.

No autonomous controls and no fallback to a conversational model for a matched
command. Captured measurements contain durations only, never utterance text.
"""
from collections import defaultdict, deque
from datetime import datetime, timezone
import json
import math
from threading import Lock
from time import monotonic, time
from uuid import uuid4
from openai.types.chat import ChatCompletionMessageFunctionToolCall
from .ActionPermissions import permission_mode


def state_dict(value):
    return value.model_dump() if hasattr(value,'model_dump') else value or {}


class LatencyMeasurements:
    FIELDS = ('capture_to_stt_ms','intent_ms','dispatch_ms','confirmation_ms','end_to_end_ms')

    def __init__(self):
        self.values=defaultdict(lambda:deque(maxlen=256))
        self.lock=Lock()

    def record(self,key,value):
        if key in self.FIELDS and isinstance(value,(int,float)) and math.isfinite(value) and value>=0:
            with self.lock: self.values[key].append(value)

    def summary(self):
        with self.lock:
            result={}
            for key in self.FIELDS:
                values=sorted(self.values[key]);n=len(values)
                result[key]={'samples':n, 'median':(values[(n-1)//2]+values[n//2])/2 if n else None,
                             'p95':values[max(0,math.ceil(.95*n)-1)] if n else None}
        return {'milliseconds':result, 'status':'Only observed samples; missing values are unavailable. Confirmation is observed state, not causal proof.'}


class CombatCommandRouter:
    def __init__(self,provider,helper,clock=monotonic,wall=time):
        self.provider,self.helper,self.clock,self.wall=provider,helper,clock,wall
        self.session=uuid4().hex
        self.metrics=LatencyMeasurements()
        self.handled={}
        self.lock=Lock()

    def allows_model_action(self,name):
        # Unmatched/low-confidence dialogue cannot route around the exact parser.
        controls = {'npcOrder','launchSLF','targetSubmodule','managePowerDistribution','deployHeatSink'}
        return not self.provider.settings.get('enabled',True) or name not in controls

    def handle(self,event,states):
        if not self.provider.settings.get('enabled',True):
            return None
        started=self.clock()
        command=self.provider.parse_order(event.content)
        self.metrics.record('intent_ms',(self.clock()-started)*1000)
        if command is None:
            return None
        timing=getattr(event,'input_timing',None) or {}
        capture=timing.get('capture_completed')
        stt=timing.get('stt_completed')
        if getattr(event,'input_source',None)=='voice' and isinstance(capture,(int,float)) and isinstance(stt,(int,float)):
            self.metrics.record('capture_to_stt_ms',(stt-capture)*1000)
        settings=self.provider.settings
        if not settings.get('enabled',True) or not settings.get('fast_commands',False):
            return 'Not executed: fast combat controls are disabled in TARS Combat settings.'
        try:
            parsed=datetime.fromisoformat(event.timestamp.replace('Z','+00:00'))
            at=parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()
        except (ValueError,TypeError,AttributeError):
            return 'Not executed: command timestamp unavailable.'
        if not -2<=self.wall()-at<=10:
            return 'Not executed: command is stale.'
        if getattr(event,'input_session',None) != self.session:
            return 'Not executed: this command belongs to a different or unknown input session.'
        source=getattr(event,'input_source','unknown')
        confidence=getattr(event,'input_confidence',None)
        if source=='voice' and (not isinstance(confidence,(int,float)) or isinstance(confidence,bool) or not .9<=confidence<=1):
            return 'Not executed: speech confidence is unavailable or too low. Use a typed command.'
        if source not in ('text','voice'):
            return 'Not executed: command input provenance unavailable.'
        config=self.helper._config
        if not config.get('tools_var') or not config.get('game_actions_var') or config.get('allowed_actions',{}).get(command['permission']) is not True:
            return 'Not executed: this control is disabled in TARS action settings.'
        mode=permission_mode(config,command['permission'])
        if mode!='allow':
            return 'Not executed: combat fast controls require an explicit Allow action permission; Ask and Block are respected.'
        descriptor=self.helper._action_manager.actions.get(command['name'])
        if not descriptor or descriptor.get('permission')!=command['permission']:
            return 'Not executed: the permitted built-in action is unavailable.'
        snapshot=self.provider.snapshot()
        status=state_dict(states.get('CurrentStatus'))
        flags=status.get('flags',{})
        age=snapshot.get('status_age_seconds')
        if age is None or age>3 or not (flags.get('InMainShip') or flags.get('InFighter')):
            return 'Not executed: current piloted-ship telemetry is unavailable.'
        if any(flags.get(k) for k in ('Docked','Landed','Supercruise')) or status.get('GuiFocus') not in (None,'NoFocus'):
            return 'Not executed: ship or UI state does not permit a tactical control.'
        kind=command['kind']
        target=snapshot.get('target')
        if kind in ('subsystem','fighter_attack') and (not target or target['stale'] or not target['scan_complete']):
            return 'Not executed: a fresh, fully scanned explicit target is required.'
        if kind.startswith('fighter_'):
            if not flags.get('InMainShip'):
                return 'Not executed: fighter orders require commander control of the mothership.'
            fighters=state_dict(states.get('ShipInfo')).get('Fighters',[])
            if kind=='fighter_launch':
                if not settings.get('experimental_launch',False):
                    return 'Not executed: experimental fighter launch UI is disabled pending live validation.'
                if not any(f.get('Status')=='Ready' for f in fighters) or any(f.get('Status')=='Launched' for f in fighters):
                    return 'Not executed: a ready fighter and clear launch state are required.'
            elif not any(f.get('Status')=='Launched' and f.get('Pilot')=='NPC Crew' for f in fighters):
                return 'Not executed: no confirmed NPC fighter is launched.'
        if kind=='heat_sink' and not flags.get('InMainShip'):
            return 'Not executed: heat sink control requires the mothership.'
        # Reserve one execution per user event even if delivery or a worker fails.
        identity=(event.timestamp,event.processed_at)
        with self.lock:
            if identity in self.handled:
                return 'Not executed: this command event was already handled.'
            self.handled[identity]=True
            while len(self.handled)>256: self.handled.pop(next(iter(self.handled)))
        call=ChatCompletionMessageFunctionToolCall(id='combat_'+uuid4().hex,type='function',
             function={'name':command['name'],'arguments':json.dumps(command['args'])})
        dispatch=self.clock()
        result=self.helper._action_manager.runAction(call,states)
        self.metrics.record('dispatch_ms',(self.clock()-dispatch)*1000)
        content=str(result.get('content',''))
        if content.startswith(('Not executed','ERROR','Error')):
            return 'Not executed: the action was denied or failed. Check action diagnostics.'
        confirmation=self.clock()
        observed=False
        try:
            if kind in ('pips','balance'):
                def expected(state):
                    pips=state_dict(state).get('Pips') or {}
                    return pips.get('system')==4 if kind=='pips' else all(pips.get(k)==2 for k in ('system','engine','weapons'))
                self.helper._event_manager.wait_for_condition('CurrentStatus',expected,timeout=2)
                observed=True
            elif kind=='subsystem':
                original=state_dict(states.get('Target'))
                def expected(state):
                    state=state_dict(state)
                    return (state.get('Ship'),state.get('PilotName'))==(original.get('Ship'),original.get('PilotName')) and state.get('Subsystem')==command['args']['subsystem']
                self.helper._event_manager.wait_for_condition('Target',expected,timeout=2)
                observed=True
            elif kind=='fighter_launch':
                def expected(state):
                    fighters=state_dict(state).get('Fighters',[])
                    return any(f.get('Status')=='Launched' and f.get('Pilot')=='NPC Crew' for f in fighters)
                self.helper._event_manager.wait_for_condition('ShipInfo',expected,timeout=2)
                observed=True
        except TimeoutError:
            pass
        if observed:
            self.metrics.record('confirmation_ms',(self.clock()-confirmation)*1000)
        if source=='voice' and isinstance(capture,(int,float)):
            self.metrics.record('end_to_end_ms',(self.clock()-capture)*1000)
        return 'Requested tactical state observed.' if observed else 'Command sent; game-state outcome unconfirmed.'

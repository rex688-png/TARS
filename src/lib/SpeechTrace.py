"""Opt-in, content-free observations. Never participates in speech decisions."""
import hashlib
import logging
import os
import sys
from contextvars import ContextVar
from contextlib import contextmanager
from time import monotonic
from functools import wraps
from uuid import uuid4

enabled = os.getenv('TARS_SPEECH_TRACE', '') == '1'
current = ContextVar('speech_trace', default=None)
current_line = ContextVar('speech_line', default=None)
current_generation = ContextVar('speech_generation', default=None)
_salt = uuid4().bytes
_logger = logging.getLogger('tars.speech')
_console_enabled = enabled
_recorder = None
current_event = ContextVar('blackbox_event', default=None)
current_reservation = ContextVar('blackbox_reservation', default=None)


def new_id():
    return uuid4().hex if enabled else None


def emit(stage, *, trace_id=None, **fields):
    if not enabled:
        return
    try:
        private = fields.pop('_private', None)
        fields.setdefault('component', {'event':'event','historical':'event','conversation':'event','plugin':'plugin','journal':'journal','generation':'model','stt':'stt','transcription':'stt','tts':'tts','playback':'tts','line':'tts','combat':'combat','prompt':'prompt','tool':'tool','chatter':'chatter','reply':'assistant','response':'assistant'}.get(stage.split('_')[0],'speech'))
        row = {'schema_version':1, 'stage':stage, 'trace_id':trace_id or current.get(),
            'event_id':current_event.get(), 'line_id':current_line.get(),
            'generation_id':current_generation.get(), 'delivery_id':current_line.get(), 'reservation_id':current_reservation.get(), **fields}
        if 'severity' not in row and (stage.endswith('_failed') or stage=='provider_rejected'): row['severity']='error'
        if _recorder is not None:
            _recorder.record(row, private)
        # Preserve legacy opt-in console observations, without duplicating automatic
        # Black Box records into ordinary logs or exposing verbose context there.
        if _console_enabled or _recorder is None:
            _logger.info('speech_trace', extra={'speech_trace':row})
    except Exception:
        pass  # Diagnostics must never influence speech/actions/callbacks.


def start_blackbox(root):
    global _recorder, enabled
    try:
        from .BlackBox import Recorder
        if _recorder is None:
            _recorder = Recorder(root)
            import threading
            previous_hook=threading.excepthook
            def report_worker_failure(args):
                emit('worker_unhandled_exception',component='application',error_type=getattr(args.exc_type,'__name__','not_reported'),severity='error')
                previous_hook(args)
            threading.excepthook=report_worker_failure
        enabled = True
    except Exception:
        pass
    return _recorder


def stop_blackbox():
    try:
        if _recorder is not None: _recorder.close()
    except Exception: pass


def identity(value):
    try:
        return _recorder.identity(value) if _recorder is not None else hashlib.blake2s(str(value)[:512].encode('utf-8'), key=_salt,digest_size=12).hexdigest()
    except Exception: return None


def safe_event_id(event):
    try: return event_fields(event).get('event_id')
    except Exception: return None


@contextmanager
def event_scope(event):
    token = current_event.set(safe_event_id(event))
    try: yield
    finally: current_event.reset(token)


def operation(component, stage):
    """Observe existing STT/tool operations, including raised failures; never retry."""
    def decorate(method):
        @wraps(method)
        def wrapped(*args, **kwargs):
            if not enabled: return method(*args, **kwargs)
            started = monotonic()
            token = current.set(current.get() or new_id())
            op = new_id()
            emit(stage+'_started',component=component,operation_id=op)
            try:
                result=method(*args, **kwargs)
            except Exception as exc:
                emit(stage+'_failed',component=component,operation_id=op,
                    error_type=type(exc).__name__,severity='error',duration_ms=(monotonic()-started)*1000)
                raise
            else:
                emit(stage+'_returned',component=component,operation_id=op,duration_ms=(monotonic()-started)*1000)
                return result
            finally: current.reset(token)
        return wrapped
    return decorate


def event_fields(event):
    if not enabled:
        return {}
    # Hash event identity, never its payload. Only known trigger labels are emitted.
    event_identity = ':'.join((type(event).__name__, str(getattr(event, 'kind', '')),
                         str(getattr(event, 'timestamp', '')),
                         str(getattr(event, 'plugin_event_name', ''))))
    data = getattr(event, 'plugin_event_content', getattr(event, 'content', getattr(event,'status',{})))
    data = data if isinstance(data,dict) else {}
    event_identity += ':' + str(data.get('id','')) + ':' + str(data.get('system_address',data.get('SystemAddress',''))) + ':' + str(data.get('body_id',data.get('BodyID','')))
    plugin_name = getattr(event, 'plugin_event_name', None)
    known = {'TARSChatter', 'TARSVisualTest', 'TARSExplorerTarget',
             'TARSNavigatorTarget', 'TARSObservatoryFact', 'TARSCombatAlert'}
    origin = plugin_name if plugin_name in known else getattr(event, 'kind', 'unknown')
    return {'trigger': origin if origin in known | {'user', 'tool', 'game', 'status', 'projected', 'plugin', 'quest'} else 'other',
            'event_id': hashlib.blake2s(event_identity.encode('utf-8'), key=_salt, digest_size=12).hexdigest(),
            'journal_id':identity(data['id']) if isinstance(data.get('id'),str) else None,
            'input_source':getattr(event,'input_source',None),'input_confidence':getattr(event,'input_confidence',None),
            'source': type(event).__name__, 'historic':getattr(event,'historic',False),
            'event_type':data.get('event'), 'planet_class':data.get('PlanetClass',data.get('planet_class')),
            'terraformable':data.get('TerraformState')=='Terraformable' if 'TerraformState' in data else data.get('terraformable'),
            'body_identity_known':data.get('BodyID',data.get('body_id')) is not None,
            'body_count':data.get('body_count',data.get('Count')),
            'signal_count':len(data.get('Signals',[])) if isinstance(data.get('Signals'),list) else None,
            'scan_stage':data.get('ScanStage'), 'code':data.get('code'), 'reservation_id':data.get('_speech_admission') or current_reservation.get(),
            'hull_health':data.get('Health',data.get('HullHealth')), 'total_reward':data.get('TotalReward'),
            'fighter':data.get('Fighter'),'player_pilot':data.get('PlayerPilot'),'shields_up':data.get('ShieldsUp'),
            **{key:(data.get('flags') or {}).get(flag) for key,flag in (('in_danger','InDanger'),('in_fighter','InFighter'),('in_main_ship','InMainShip')) if isinstance(data.get('flags'),dict)}}


def observe_event(stage, event, **fields):
    if enabled:
        try:
            data = event_fields(event)
            if current_event.get() and current_event.get()!=data.get('event_id'):
                data['parent_event_id']=current_event.get()
            content=getattr(event,'content',None)
            private={'user_input' if getattr(event,'kind',None)=='user' else 'final_output':content} if stage=='conversation_submitted' and getattr(event,'kind',None) in ('user','assistant') and isinstance(content,str) else None
            if stage in ('event_received','plugin_dispatched'):
                evidence=getattr(event,'plugin_event_content',getattr(event,'content',{}))
                if isinstance(evidence,dict):
                    allowed={'BodyName','BodyID','SystemAddress','PlanetClass','TerraformState','Health','Fighter','WasDiscovered','WasMapped','body','body_id','system','planet_class','terraformable','callout_kind','mapping_recommendation','confirmed_genuses'}
                    selected={k:v for k,v in evidence.items() if k in allowed and type(v) in (str,int,float,bool,type(None))}
                    if selected:
                        import json
                        private={'input_evidence':json.dumps(selected,ensure_ascii=False)}
            emit(stage, **{**data, **fields}, _private=private)
        except Exception:
            pass


def observe_message(message):
    """Translate existing Chatter decisions to fixed codes without copying text.

    No new plugin wrapper or suppression logic. Unknown messages are ignored.
    Timer-thread decisions may have no reply trace: they precede dispatch.
    """
    if not enabled or not isinstance(message, str):
        return
    decisions = (
        ('TARS Explorer suppressed proactive callout: commander reply has priority.', 'explorer_decision', 'direct_priority'),
        ('TARS Explorer suppressed repeated zero-planet composition ', 'explorer_decision', 'repeated_composition'),
        ('TARS Explorer suppressed additional zero-planet wrap-up for session novelty.', 'explorer_decision', 'session_novelty'),
        ('TARS Navigator suppressed proactive milestone: commander reply has priority.', 'navigator_decision', 'direct_priority'),
        ('TARS Chatter discarded a weak candidate (', 'candidate_discarded', 'quality_check'),
        ('TARS Chatter accepted model-selected silence.', 'candidate_discarded', 'model_skip'),
        ('TARS Chatter stayed silent: no concrete situational anchor', 'chatter_silent', 'no_anchor'),
        ('TARS Chatter gave up after exhausting fresh subjects', 'chatter_silent', 'candidates_exhausted'),
        ('TARS Chatter chose deliberate silence.', 'chatter_silent', 'random_silence'),
        ('TARS Chatter deferred: recent user activity.', 'chatter_silent', 'recent_user_activity'),
        ('TARS Chatter deferred: COVAS reply in progress.', 'chatter_silent', 'reply_in_progress'),
        ('TARS Director rejected repetitive draft (', 'candidate_discarded', 'output_guard'),
        ('TARS Chatter rejected retry (', 'candidate_discarded', 'retry_rejected'),
        ('TARS Director suppressed ', 'chatter_silent', 'routine_noise'),
        ('TARS Director retrying one transient LLM failure', 'generation_retry', 'transient_direct_request'),
        ('TARS Director accepted regenerated response.', 'candidate_accepted', 'regenerated'),
        ('TARS Director used factual fallback for ', 'candidate_accepted', 'factual_fallback'),
    )
    for prefix, stage, reason in decisions:
        if message.startswith(prefix):
            emit(stage, source='TARSExplorer' if stage=='explorer_decision' else 'TARSNavigator' if stage=='navigator_decision' else 'TARSChatter', reason=reason)
            return


def reply_scope(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        if not enabled:
            return method(*args, **kwargs)
        token = current.set(new_id())
        generation_token = current_generation.set(None)
        emit('reply_started')
        try:
            return method(*args, **kwargs)
        finally:
            emit('reply_finished')
            current_generation.reset(generation_token)
            current.reset(token)
    return wrapped


def generation(method):
    """Observe concrete calls, including Chatter's saved original bound method.

    Frame *names* identify existing paths; no frame locals/messages are read.
    Chatter wrappers and their retry/selection behavior remain untouched.
    """
    @wraps(method)
    def wrapped(*args, **kwargs):
        if not enabled:
            return method(*args, **kwargs)
        path = 'model'
        frame = sys._getframe(1)
        try:
            for _ in range(24):
                if frame is None:
                    break
                if frame.f_code.co_name == '_prepare_chatter_line':
                    path = 'chatter_candidate'
                    break
                if frame.f_code.co_name in ('guarded_generate', 'resilient_generate'):
                    path = 'chatter_guard'
                frame = frame.f_back
        finally:
            del frame
        attempt_id = new_id()
        parent = current.get() or new_id()
        token=current.set(parent)
        gen_token=current_generation.set(current_generation.get() or new_id())
        started=monotonic()
        model=args[0] if args else None
        emit('generation_started', trace_id=parent, attempt_id=attempt_id, path=path,component='model',
            model=getattr(model,'model_name',None),provider=getattr(model,'provider_name',None),
            model_id=identity(getattr(model,'model_name',None)),provider_id=identity(getattr(model,'provider_name',None)))
        try:
            result = method(*args, **kwargs)
        except Exception as exc:
            emit('generation_failed', trace_id=parent, attempt_id=attempt_id, path=path,component='model',
                duration_ms=(monotonic()-started)*1000,error_type=type(exc).__name__,severity='error')
            raise
        else:
            text=result[0] if isinstance(result,tuple) and result and isinstance(result[0],str) else None
            usage=result[2] if isinstance(result,tuple) and len(result)>2 else None
            fields={key:getattr(usage,key,None) for key in ('input_tokens','output_tokens','total_tokens','cached_tokens','retry_attempts')}
            usage_available=any(type(fields[k]) in (int,float) and fields[k]>0 for k in ('input_tokens','output_tokens','total_tokens'))
            if not usage_available: fields={k:v for k,v in fields.items() if k=='retry_attempts' and type(v) is int and v>0}
            fields['usage_available']=usage_available
            emit('generation_returned', trace_id=parent, attempt_id=attempt_id, path=path,component='model',
                duration_ms=(monotonic()-started)*1000,output_chars=len(text) if text else 0,
                _private={'final_output':text} if text else None,**fields)
            actions=result[1] if isinstance(result,tuple) and len(result)>1 else None
            if isinstance(actions,list):
                for action in actions[:32]:
                    function=getattr(action,'function',None)
                    name=getattr(function,'name',None)
                    emit('model_tool_selected',component='model',tool=name,tool_id=identity(name))
            return result
        finally:
            current_generation.reset(gen_token)
            current.reset(token)
    return wrapped


def plugin_marker(plugin):
    try:
        decisions=getattr(plugin,'_callout_decisions',None)
        return decisions[-1] if isinstance(decisions,list) and decisions else None
    except Exception: return None


def plugin_decisions(plugin, event, previous):
    """Translate existing pinned Explorer outcomes; never rerun its eligibility policy."""
    if not enabled: return
    try:
        decisions=getattr(plugin,'_callout_decisions',None)
        if not isinstance(decisions,list): return
        start=0
        for i,row in enumerate(decisions[-20:]):
            if row is previous: start=i+1
        codes=(('suppressed: history reconstruction','history_reconstruction'),
            ('suppressed: automatic callouts disabled','automatic_callouts_disabled'),
            ('suppressed: already announced','already_announced'),
            ('suppressed: same-body cooldown','same_body_cooldown'),
            ('suppressed: repeated system-level idea','repeated_system_idea'),
            ('suppressed: mapped body has no high-value','no_mapping_reason'),
            ('suppressed: helper unavailable','helper_unavailable'),
            ('not a planet/body','not_a_planet'),
            ('no noteworthy scan criteria matched','no_noteworthy_criteria'),
            ('dispatch failed:','dispatch_failed'),('dispatched','dispatched'))
        for row in decisions[-20:][start:]:
            outcome=row.get('outcome')
            reason=next((code for prefix,code in codes if isinstance(outcome,str) and outcome.startswith(prefix)),'not_reported')
            observe_event('explorer_decision',event,component='plugin',source='TARSExplorer',reason=reason,
                expected_callout=row.get('expected_callout') is True,accepted=reason=='dispatched',planet_class=row.get('planet_class'),
                count=len(row.get('reasons',[])) if isinstance(row.get('reasons'),list) else None)
    except Exception: pass


_plugin_manager = None
_sampled = {}


def attach_plugins(manager):
    global _plugin_manager
    _plugin_manager=manager
    if _recorder is not None: _recorder.sampler=sample_plugins


def sample_plugins():
    """Read exposed counters only; never invoke tools, state transitions or a model."""
    try:
        for plugin in list(_plugin_manager.plugin_list.values())[:32]:
            name=type(plugin).__name__
            if name=='TARSObservatoryBridge':
                status=getattr(plugin,'_status',{})
                for field,reason in (('ignored_historical','historical_ignored'),('ignored_non_notification','non_notification_ignored'),('malformed','malformed_record'),('relayed','relayed')):
                    value=status.get(field)
                    if type(value) is int and _sampled.get(field)!=value:
                        _sampled[field]=value
                        emit('observatory_counter',component='plugin',source=name,reason=reason,count=value)
            elif name=='TARSCombat':
                settings=getattr(plugin,'settings',{})
                values=tuple(bool(settings.get(k,default)) for k,default in (('alerts',True),('focus',True),('fast_commands',False)))
                if _sampled.get('combat')!=values:
                    _sampled['combat']=values
                    emit('combat_policy_configured',component='combat',alerts_enabled=values[0],focus_enabled=values[1],controls_enabled=values[2])
    except Exception: pass


def observe_tool_result(name, result):
    if not enabled: return
    try:
        import json
        if not isinstance(result,str) or len(result)>65536: return
        data=json.loads(result)
        if not isinstance(data,dict): return
        emit('tool_result_evidence',component='tool',tool=name,reported_ok=data.get('ok') if type(data.get('ok')) is bool else None,
            mapping_recommendation_present=isinstance(data.get('mapping_recommendation'),dict),
            reason=data.get('error') if isinstance(data.get('error'),str) else 'not_reported')
    except Exception: pass

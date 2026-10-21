"""Opt-in, content-free observations. Never participates in speech decisions."""
import hashlib
import logging
import os
import sys
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4

enabled = os.getenv('TARS_SPEECH_TRACE', '') == '1'
current = ContextVar('speech_trace', default=None)
current_line = ContextVar('speech_line', default=None)
_salt = uuid4().bytes
_logger = logging.getLogger('tars.speech')


def new_id():
    return uuid4().hex if enabled else None


def emit(stage, *, trace_id=None, **fields):
    if not enabled:
        return
    try:
        # Call sites supply only fixed labels, opaque IDs, booleans and counts.
        _logger.info('speech_trace', extra={'speech_trace': {
            'schema_version': 1, 'stage': stage,
            'trace_id': trace_id or current.get(), 'line_id': current_line.get(), **fields,
        }})
    except Exception:
        # Observability must not change generation, callbacks or playback.
        pass


def event_fields(event):
    if not enabled:
        return {}
    # Hash event identity, never its payload. Only known trigger labels are emitted.
    identity = ':'.join((type(event).__name__, str(getattr(event, 'kind', '')),
                         str(getattr(event, 'timestamp', '')),
                         str(getattr(event, 'plugin_event_name', ''))))
    plugin_name = getattr(event, 'plugin_event_name', None)
    known = {'TARSChatter', 'TARSVisualTest', 'TARSExplorerTarget',
             'TARSNavigatorTarget', 'TARSObservatoryFact'}
    origin = plugin_name if plugin_name in known else getattr(event, 'kind', 'unknown')
    return {'trigger': origin if origin in known | {'user', 'tool', 'game', 'status', 'projected', 'plugin', 'quest'} else 'other',
            'event_id': hashlib.blake2s(identity.encode(), key=_salt, digest_size=12).hexdigest(),
            'source': type(event).__name__}


def observe_event(stage, event, **fields):
    if enabled:
        try:
            emit(stage, **event_fields(event), **fields)
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
            emit(stage, source='TARSChatter', reason=reason)
            return


def reply_scope(method):
    @wraps(method)
    def wrapped(*args, **kwargs):
        if not enabled:
            return method(*args, **kwargs)
        token = current.set(new_id())
        emit('reply_started')
        try:
            return method(*args, **kwargs)
        finally:
            emit('reply_finished')
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
        emit('generation_started', trace_id=parent, attempt_id=attempt_id, path=path)
        try:
            result = method(*args, **kwargs)
        except Exception:
            emit('generation_failed', trace_id=parent, attempt_id=attempt_id, path=path)
            raise
        emit('generation_returned', trace_id=parent, attempt_id=attempt_id, path=path)
        return result
    return wrapped

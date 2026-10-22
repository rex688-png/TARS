from . import SpeechTrace as speech_trace
from pydantic.main import BaseModel
import inspect
import os
import queue
from typing import Any, Callable, TypeVar

from .Models import LLMModel, STTModel, TTSModel, EmbeddingModel
from .Logger import log
from .EDKeys import EDKeys
from .EventManager import EventManager, Projection as _Projection
from .ActionManager import ActionManager
from .SystemDatabase import SystemDatabase
from .Config import Config, save_config
from .Event import Event, PluginEvent as _PluginEvent
from .PromptGenerator import PromptGenerator
from .Assistant import Assistant

# Type alias for projected states dictionary
ProjectedStates = dict[str, BaseModel]

# reexport Projection and PluginEvent for plugins
Projection = _Projection
PluginEvent = _PluginEvent

# reexport Model base classes for plugins to extend
LLMModel = LLMModel
STTModel = STTModel
TTSModel = TTSModel
EmbeddingModel = EmbeddingModel

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .PluginManager import PluginManager
    from .PluginBase import PluginManifest

class OptionalSpeechHandle:
    """Preparation capability; dispatch atomically transfers ownership to the host."""
    def __init__(self, helper, triggered_at):
        self.helper = helper
        self.arbiter = helper._assistant.speech_arbiter()
        self.arbiter.note_cancellation(getattr(helper._assistant.tts, '_abort_revision', None))
        self.lease = self.arbiter.begin_optional(triggered_at, helper._config.get('speech_director_mode', 'observe'),
                                                  busy=helper._optional_priority_pending())
        self.allowed = self.lease.allowed
        self.enforcing = self.lease.mode == 'enforce'
        self.closed = False

    def valid(self):
        mode = self.arbiter.configure(self.helper._config.get('speech_director_mode', 'observe'))
        if mode != self.lease.mode and 'enforce' in (mode, self.lease.mode):
            return False
        self.arbiter.note_cancellation(getattr(self.helper._assistant.tts, '_abort_revision', None))
        if self.closed and self.lease.mode == 'enforce':
            return False
        return self.arbiter.optional_valid(self.lease, self.helper._optional_priority_pending())

    def dispatch(self, event):
        if not self.valid():
            return False
        def dispatch(token):
            if token is not None:
                event.plugin_event_content = {**event.plugin_event_content, '_speech_admission': token}
            self.helper.dispatch_event(event)
        return self.arbiter.dispatch_optional(self.lease, self.helper._optional_priority_pending, dispatch)

    def close(self):
        self.closed = True
        self.arbiter.release_optional(self.lease)


class PluginHelper():
    """Contains all built-inservices and managers that can be used by plugins"""

    _plugin_manager: 'PluginManager'
    _assistant: Assistant
    _prompt_generator: PromptGenerator
    _keys: EDKeys
    _vision_model: LLMModel | None = None
    _llm_model: LLMModel
    _vision_model_name: str | None = None
    _event_manager: EventManager
    _action_manager: ActionManager
    _config: Config
    _system_db: SystemDatabase
    PLUGIN_DATA_PATH: str = "plugin_data"

    def __init__(self, plugin_manager: 'PluginManager', prompt_generator: PromptGenerator, config: Config, action_manager: ActionManager, event_manager: EventManager, llm_model: LLMModel, vision_model: LLMModel | None,
                     system_db: SystemDatabase, ed_keys: EDKeys, assistant: Assistant):
        self._plugin_manager = plugin_manager
        self._prompt_generator = prompt_generator
        self._keys = ed_keys
        self._system_db = system_db
        self._vision_model = vision_model
        self._llm_model = llm_model
        self._event_manager = event_manager
        self._action_manager = action_manager
        self._config = config
        self._assistant = assistant

    def get_plugin_data_path(self, plugin_manifest: 'PluginManifest') -> str:
        """Get a plugin data path, from the plugin data folder"""
        plugin_data_path = os.path.abspath(os.path.join(self.PLUGIN_DATA_PATH, plugin_manifest.guid))
        if not os.path.exists(plugin_data_path):
            os.makedirs(plugin_data_path, exist_ok=True)
        return plugin_data_path

    _ActionModelT = TypeVar('_ActionModelT', bound=BaseModel)

    def register_action(self, name: str, description: str, parameters: type[_ActionModelT], method: Callable[[_ActionModelT, dict], str], action_type="ship", input_template: Callable[[dict, dict], str]|None=None):
        """Register an action"""
        signature = inspect.signature(method)
        positional = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.kind
            in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        ]
        has_varargs = any(
            parameter.kind == inspect.Parameter.VAR_POSITIONAL
            for parameter in signature.parameters.values()
        )
        required_keyword_only = [
            parameter.name
            for parameter in signature.parameters.values()
            if parameter.kind == inspect.Parameter.KEYWORD_ONLY
            and parameter.default is inspect.Parameter.empty
        ]
        if required_keyword_only:
            raise TypeError(
                f"Plugin action '{name}' has unsupported required keyword-only "
                f"parameters: {', '.join(required_keyword_only)}"
            )
        if has_varargs or len(positional) == 2:
            invoke = lambda model, context: method(model, context)
        elif len(positional) == 1:
            invoke = lambda model, context: method(model)
        else:
            raise TypeError(
                f"Plugin action '{name}' must accept one or two positional arguments; "
                f"got {signature}"
            )

        def _wrapper(args: dict, context: dict) -> str:
            try:
                model = parameters(**args)
                return invoke(model, context)
            except Exception as e:
                log('error', f"Plugin action '{name}' raised an exception: {e}")
                return f"Error executing action {name}: {str(e)}"

        self._action_manager.registerAction(name=name, description=description, parameters=parameters.model_json_schema(), method=_wrapper, action_type=action_type, input_template=input_template)

    def register_projection(self, projection: Projection):
        """Register a projection to maintain state over time
        
        :param projection: The projection to register,
        """
        self._event_manager.register_projection(projection, raise_error = False)
        
    def register_sideeffect(self, sideeffect: Callable[[Event, dict[str, Any]], None]):
        """Register a sideeffect to react to events programmatically
        
        :param sideeffect: A callable that takes any incoming Event and the current projected states dict
        """
        def _sideeffect_wrapper(event: Event, context: dict[str, Any]):
            try:
                sideeffect(event, context)
            except Exception as e:
                log('error', f"Plugin sideeffect raised an exception: {e}")
        self._event_manager.register_sideeffect(_sideeffect_wrapper)

    def dispatch_event(self, event: PluginEvent):
        """Dispatch an event from an outside source
        
        :param event: The event to dispatch
        """
        if not isinstance(event, PluginEvent):
            raise ValueError("Event must be of type PluginEvent")
        speech_trace.observe_event("plugin_dispatched", event)
        self._event_manager.incoming.put(event)

    def record_chatter_diagnostic(self, reason):
        if reason in ('scheduled', 'cooldown', 'assistant_activity', 'game_activity',
                      'user_activity', 'host_busy', 'deliberate_silence', 'context_missing',
                      'context_used', 'quality_rejected', 'host_admission', 'candidate_accepted',
                      'dispatched', 'model_skip', 'generation_failed', 'session_context', 'model_unavailable'):
            speech_trace.emit('chatter_opportunity', source='chatter', reason=reason)

    def preview_optional_speech(self) -> bool:
        """Legacy advisory preview; preparation should use reserve_optional_speech."""
        _, states = self._event_manager.get_current_state()
        return self._assistant.speech_arbiter().preview_optional(
            states, self._config.get("speech_director_mode", "observe"))

    def _optional_priority_pending(self):
        from .Event import ConversationEvent, ToolEvent, GameEvent, StatusEvent
        from .SpeechArbiter import source
        assistant = self._assistant
        if assistant.reply_pending or assistant.is_replying:
            return True
        events = list(assistant.pending)
        incoming = getattr(self._event_manager, 'incoming', None)
        if isinstance(incoming, queue.Queue):
            with incoming.mutex:
                events += list(incoming.queue)
        for event in events:
            if getattr(event, 'do_not_reply', False):
                continue
            if isinstance(event, ToolEvent) or (isinstance(event, ConversationEvent) and event.kind in ('user', 'user_speaking')):
                return True
            if source(event) in ('explorer', 'observatory', 'navigator'):
                return True
            data = event.content if isinstance(event, GameEvent) else event.status if isinstance(event, StatusEvent) else {}
            if data.get('event') in assistant.enabled_game_events:
                return True
        return False

    def reserve_optional_speech(self, triggered_at):
        return OptionalSpeechHandle(self, triggered_at)

    def optional_speech_event_valid(self, event):
        data = getattr(event, 'plugin_event_content', {})
        token = data.get('_speech_admission') if isinstance(data, dict) else None
        if token is None or self._config.get('speech_director_mode', 'observe') != 'enforce':
            return True
        return self._assistant.speech_arbiter().optional_event_valid(token)

    def cancel_optional_speech(self):
        self._assistant.speech_arbiter().cancel_optional('stopped')

    def send_key(self, key_name: str, *args, **kwargs):
        """Send a key"""
        self._keys.send(key_name, *args, **kwargs)

    def register_event(self, name: str, should_reply_check: Callable[[PluginEvent], bool], prompt_generator: Callable[[PluginEvent], str]):
        """Register an event type

        :param name: The name of the plugin event to register
        :param should_reply_check: A callable that takes a PluginEvent and returns True if the assistant should reply to it, False otherwise
        :param prompt_generator: A callable that takes a PluginEvent and returns a string prompt to add to the assistant conversation
        """
        def _prompt_handler(event: Event) -> str| None:
            if not isinstance(event, PluginEvent):
                return None
            if event.plugin_event_name != name:
                return None
            try:
                response = prompt_generator(event)
            except Exception as e:
                log('error', f"Plugin prompt_generator raised an exception: {e}")
                return None
            return response
        self._prompt_generator.register_prompt_event_handler(_prompt_handler)
        
        def _should_reply_check(event: Event, context: dict[str, Any]) -> bool | None:
            if not isinstance(event, PluginEvent):
                return None
            if event.plugin_event_name != name:
                return None
            try:
                selected = should_reply_check(event)
                if not selected and isinstance(event.plugin_event_content, dict):
                    token = event.plugin_event_content.get('_speech_admission')
                    if token is not None:
                        self._assistant.speech_arbiter().discard_optional(token)
                speech_trace.observe_event("plugin_reply_check", event, selected=bool(selected))
                return selected
            except Exception as e:
                if isinstance(event.plugin_event_content, dict):
                    token = event.plugin_event_content.get('_speech_admission')
                    if token is not None:
                        self._assistant.speech_arbiter().discard_optional(token)
                speech_trace.observe_event("plugin_reply_check_failed", event)
                log('error', f"Plugin should_reply_check raised an exception: {e}")
                return False
        self._assistant.register_should_reply_handler(_should_reply_check)
        
    def register_status_generator(self, status_generator: Callable[[ProjectedStates], list[tuple[str, Any]]]):
        """
        Register a status generator callback, for adding stuff to the models status context (Like ship info).
            
        :param status_generator: A callable that takes the current projected states and returns a list of (title, content) tuples.
        """
        def _status_generator_wrapper(states: ProjectedStates) -> list[tuple[str, Any]]:
            try:
                return status_generator(states)
            except Exception as e:
                log('error', f"Plugin status_generator raised an exception: {e}")
                return []
        self._prompt_generator.register_status_generator(_status_generator_wrapper)

    def wait_for_condition(self, projection_name: str, condition_fn, timeout=None):
        """Block until `condition_fn` is satisfied by the current or future
        state of the specified projection.

        :param projection_name: Name/identifier of the projection to watch.
        :param condition_fn: A callable that takes a dict (the current projection state)
                             and returns True/False.
        :param timeout: Optional timeout (seconds).
        :return: The state dict that satisfied the condition.
        :raises TimeoutError: If the condition isn't met within `timeout`.
        """
        def _condition_fn_wrapper(state: dict) -> bool:
            try:
                return condition_fn(state)
            except Exception as e:
                log('error', f"Plugin wait_for_condition condition_fn raised an exception: {e}")
                return False
        return self._event_manager.wait_for_condition(projection_name, _condition_fn_wrapper, timeout)

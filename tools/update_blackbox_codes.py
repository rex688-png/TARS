"""Regenerate the public metadata label catalogue after reviewing new instrumentation."""
import ast,re
from pathlib import Path
root=Path(__file__).resolve().parents[1]
labels={'not_reported','standard','verbose','application','speech','assistant','event','info','warning','error','model','tool','stt','tts','journal','plugin','prompt','projection','combat','record','active','recovering','idle','returned','exception','unavailable','allow','ask','block','TimeoutError','ConnectionError','OSError','ValueError','RuntimeError','LLMError','APIStatusError','RateLimitError','APIConnectionError','APITimeoutError','JSONDecodeError','CancelledError','ReadTimeout','FakeLLM','OpenAI','OpenAIResponsesLLMModel','Water world','Earth-like world','Ammonia world'}
files=list((root/'src/lib').rglob('*.py'))+list((root/'vendor/tars-plugins/plugins').rglob('*.py'))+[root/'src/Chat.py']
for p in files:
 if p.name in ('BlackBoxCodes.py',):continue
 try:tree=ast.parse(p.read_text(encoding='utf-8'))
 except (ValueError,UnicodeError,SyntaxError):continue
 for n in ast.walk(tree):
  if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and (isinstance(n,ast.ClassDef) or p.name=='Actions.py'):labels.add(n.name)
  if isinstance(n,ast.Constant) and isinstance(n.value,str):
   value=n.value
   targeted=p.name in {'SpeechTrace.py','SpeechArbiter.py','SpeechPolicy.py','ExplorationSpeech.py','ResponsePresentation.py','BlackBox.py','BlackBoxCommands.py','ActionManager.py','STT.py','TTS.py','EventManager.py','PluginHelper.py','Assistant.py','EDJournal.py','Chat.py','TARSChatter.py','TARSChatterSession.py','TARSCombat.py','CombatState.py'}
   if re.fullmatch(r'[A-Za-z][A-Za-z0-9_.:-]{0,63}',value) and (targeted or value.startswith(('tars_','TARS','gpt-')) or (p.name=='EventModels.py' and value[:1].isupper())):labels.add(value)
   if p.name=='SpeechTrace.py' and value.endswith('_started'):labels.update([value[:-8]+'_returned',value[:-8]+'_failed'])
labels.update({'LIVE','CURRENT SNAPSHOT','LAST KNOWN','openai','openrouter','edge-tts','mistral','custom','plugin','parakeet','pocket-tts','local-ai-server','ollama','invalid_prompt','invalid_api_key','rate_limit_exceeded','insufficient_quota','context_length_exceeded','model_not_found','provider_error','PermissionError','FileNotFoundError','TypeError','IndexError','MemoryError','UnicodeDecodeError','UnicodeEncodeError','ConnectionResetError'})
labels.update({'transcription_started','transcription_returned','transcription_failed','tool_execution_started','tool_execution_returned','tool_execution_failed','session_started','session_stopped','recording_mode_changed','recording_limits_changed','records_dropped','previous_session_unclean'})
import pprint
(root/'src/lib/BlackBoxCodes.py').write_text('"""Public diagnostic schema labels. Unknown producer strings are never copied verbatim."""\nLABELS = frozenset('+pprint.pformat(sorted(labels),width=100)+')\n',encoding='utf-8')
print(len(labels))

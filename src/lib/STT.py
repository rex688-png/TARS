from . import SpeechTrace as speech_trace
import queue
import threading
import traceback
from time import sleep, time, monotonic
from typing import Literal, final

import pyaudio
import speech_recognition as sr
from pysilero_vad import SileroVoiceActivityDetector

from .Logger import (
    AudioUsageStats,
    LatencyUsageStats,
    TextUsageStats,
    log,
    log_stt_usage,
    observe,
    show_chat_message,
)
from .Models import STTModel, LLMError


@final
class STTResult:
    def __init__(self, text: str, audio: sr.AudioData, timestamp: float, *, capture_completed: float | None = None, stt_completed: float | None = None, confidence: float | None = None):
        self.text = text
        self.audio = audio
        self.timestamp = timestamp
        self.capture_completed = capture_completed
        self.stt_completed = stt_completed
        self.confidence = confidence
        self.trace_id = speech_trace.current.get()

    def __str__(self):
        return self.text

    def __repr__(self):
        return self.text

@final
class STT:
    listening = False
    recording = False

    def __init__(self, stt_model: STTModel | None, input_device_name, required_word=None):
        self._stop_event = threading.Event()
        self._worker_thread = None
        self.resultQueue = queue.Queue()
        self.listening = False
        self.recording = False
        self.stt_model = stt_model
        self.vad = SileroVoiceActivityDetector()
        self.input_device_name = input_device_name
        self.required_word = required_word
        self.continuous_listening_paused = False

        self.rate=16000
        self.sample_width = pyaudio.get_sample_size(pyaudio.paInt16)
        self.frames_per_buffer=self.vad.chunk_bytes() // pyaudio.get_sample_size(pyaudio.paInt16)

        self.vad_threshold = 0.2
        self.phrase_end_pause = 1.0

    def listen_once_start(self):
        log('debug', 'listen_once_start')
        if self.stt_model is None:
            return
        if self._stop_event.is_set() or (self._worker_thread and self._worker_thread.is_alive()):
            return
        self.listening = True
        self._worker_thread = threading.Thread(target=self._listen_once_thread, daemon=True)
        self._worker_thread.start()

    def listen_once_end(self):
        log('debug', 'listen_once_end')
        self.listening = False

    def _listen_once_thread(self):
        """
        Push to talk like functionality, immediately records audio and sends it to the OpenAI API, bypassing the VAD.
        """
        # print('Running STT in PTT mode')
        log('debug', 'listen_once_thread start')
        source = None
        text = None
        try:
            source = self._get_microphone()
            self.recording = True
            timestamp = time()
            frames = []
            while self.listening:
                buffer = self._read_stream_buffer(source)
                if len(buffer) == 0: break  # reached end of the stream
                frames.append(buffer)

            source.close()
            source = None
            audio_raw = b''.join(frames)
            audio_data = sr.AudioData(audio_raw, self.rate, self.sample_width)
            capture_completed = monotonic()
            text = self._transcribe(audio_data)
            stt_completed = monotonic()
        finally:
            self.recording = False
            if source is not None:
                source.close()
        
        if text and not self._stop_event.is_set():
            result=STTResult(text, audio_data, timestamp, capture_completed=capture_completed, stt_completed=stt_completed)
            result.trace_id=getattr(self,'_diagnostic_trace_id',None)
            self.resultQueue.put(result)
        
        log('debug', 'listen_once_thread end')

    def listen_continuous(self):
        if self._stop_event.is_set() or (self._worker_thread and self._worker_thread.is_alive()):
            return
        if self.stt_model is None:
            return
        self.listening = True
        self._worker_thread = threading.Thread(target=self._listen_continuous_thread, daemon=True)
        self._worker_thread.start()
                        
    def _listen_continuous_thread(self):
        backoff = 1
        while self.listening:
            try: 
                self._listen_continuous_loop()
            except Exception as e:
                self.recording = False
                speech_trace.emit('stt_worker_recovery',component='stt',reason='worker_failure',severity='warning')
                log('error', 'An error occurred during speech recognition', e, traceback.format_exc())
                show_chat_message('error', 'Speech recognition error:', e)
                if self._stop_event.wait(backoff):
                    break
                log('info', 'Attempting to restart speech recognition after failure')
                backoff = min(backoff * 2, 30)

    def _listen_continuous_loop(self):
        source: pyaudio.Stream = self._get_microphone()
        try:
            timestamp = time()
            frames = []
            activity = []
            while self.listening:
                buffer = self._read_stream_buffer(source)
                if self.continuous_listening_paused:
                    self.recording = False
                    frames = []
                    activity = []
                    timestamp = time()
                    continue
                if len(buffer) == 0: break  # reached end of the stream
                frames.append(buffer)
                frames_duration = len(frames) * self.frames_per_buffer / self.rate
                activity.append(self.vad(buffer))
                if frames_duration > 0.5:
                    #log('debug','checking for voice activity in', frames_duration, 'seconds of audio')
                    audio_raw = b''.join(frames)
                    if all([v < self.vad_threshold for v in activity]):
                        # no voice detected in the recording so far, so clear the buffer
                        # and keep only last 0.1 seconds of audio for the next iteration
                        #log('debug','no voice detected, clearing buffer')
                        keep = int(0.1 * self.rate / self.frames_per_buffer)
                        frames = frames[-keep:]
                        activity = activity[-keep:]
                        timestamp = time()
                        continue
                    else:
                        self.recording = True
                        # we have voice activity in current recording
                        # check if there is voice in the last phrase_end_pause seconds
                        #log('debug','voice detected, checking for pause in the last phrase_end_pause seconds')
                        end_slice = int(self.phrase_end_pause * self.rate / self.frames_per_buffer)
                        activity_end_slice = activity[-end_slice:]
                        if all([v < self.vad_threshold for v in activity_end_slice]):
                            # no voice in the last 0.5 seconds, so we know the user has stopped speaking
                            # so we can transcribe the audio
                            #log('debug','no voice detected in the last 0.5 seconds, transcribing')
                            audio_data = sr.AudioData(audio_raw, self.rate, self.sample_width)
                            capture_completed = monotonic()
                            text = self._transcribe(audio_data)
                            stt_completed = monotonic()
                            frames = []
                            activity = []
                            if text and not self._stop_event.is_set():
                                result=STTResult(text, audio_data, timestamp, capture_completed=capture_completed, stt_completed=stt_completed)
                                result.trace_id=getattr(self,'_diagnostic_trace_id',None)
                                self.resultQueue.put(result)
                            self.recording = False
        finally:
            self.recording = False
            source.close()

    def _read_stream_buffer(self, source: pyaudio.Stream) -> bytes:
        try:
            return source.read(self.frames_per_buffer, exception_on_overflow=False)
        except TypeError:
            return source.read(self.frames_per_buffer)
        except OSError as e:
            if getattr(e, 'errno', None) == -9981:
                log('warn', 'Audio input overflow detected, dropping one microphone chunk')
                return b'\x00' * self.frames_per_buffer * self.sample_width
            raise

    def _get_microphone(self) -> pyaudio.Stream:
        audio = pyaudio.PyAudio()

        host_api = audio.get_default_host_api_info()

        try:
            device_index = 0
            for i in range(host_api.get('deviceCount')):
                device = audio.get_device_info_by_host_api_device_index(host_api.get('index'), i)
                if device['name'] == self.input_device_name:
                    device_index = device.get('index')
                    break

            source = audio.open(
                input_device_index=device_index,
                format=pyaudio.paInt16,
                channels=1,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.frames_per_buffer
            )
        except Exception as e:
            log('error', 'Failed to open microphone', e, traceback.format_exc())
            speech_trace.emit('stt_device_fallback',component='stt',reason='device_unavailable',severity='warning')
            log('error', 'Fallback to default microphone')
            source = audio.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=self.rate,
                input=True,
                frames_per_buffer=self.frames_per_buffer
            )
        speech_trace.emit('stt_capture_started',component='stt')
        return source

    @speech_trace.operation('stt','transcription')
    @observe()
    def _transcribe(self, audio: sr.AudioData) -> str:
        self._diagnostic_trace_id=speech_trace.current.get()
        speech_trace.emit('stt_capture_completed',component='stt')
        log('debug', 'Transcribing audio...')
        if self.stt_model is None:
            raise ValueError('Speech recognition is disabled')
        
        audio_raw = audio.get_raw_data(convert_rate=16000, convert_width=2)
        audio_length = len(audio_raw) / 2 / 16000
        if audio_length < 0.2:
            speech_trace.emit('stt_discarded',component='stt',reason='short_audio')
            log('debug', 'skipping short audio')
            return ''
        if all([a < self.vad_threshold for a in self.vad.process_chunks(audio_raw)]):
            speech_trace.emit('stt_discarded',component='stt',reason='no_voice')
            log('debug', 'skipping audio without voice')
            return ''


        text = None
        start_time = time()
        
        try:
            text = self.stt_model.transcribe(audio)
        except LLMError as e:
            speech_trace.emit('stt_failed',component='stt',reason='provider_error',severity='error')
            log('error', 'STT Error:', e)
            show_chat_message('error', 'STT Error:', str(e))
            return ''
        except Exception as e:
            speech_trace.emit('stt_failed',component='stt',reason='provider_error',severity='error')
            log('error', 'STT Error:', e, traceback.format_exc())
            return ''

        end_time = time()
        log('debug', f'Response time STT', end_time - start_time)

        filter = ['', 'COVAS, give me a status update... and throw in something inspiring, would you?']
        if not text or text.strip() in filter:
            return ''
        
        if self.required_word and self.required_word.lower() not in text.lower():
            return ''

        log_stt_usage(
            "speech",
            provider=getattr(self.stt_model, "provider_name", None),
            model_name=getattr(self.stt_model, "model_name", None),
            latency_usage=LatencyUsageStats(response_ms=(end_time - start_time) * 1000),
            audio_usage=AudioUsageStats(input_audio_duration_ms=audio_length * 1000),
            text_usage=TextUsageStats(output_chars=len(text)),
        )

        # print("transcription received", text)
        return text

    def stop(self):
        self._stop_event.set()
        self.listening = False
        worker = self._worker_thread
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=2)

    def pause_continuous_listening(self, pause: bool):
        self.continuous_listening_paused = pause

# if __name__ == "__main__":
#     openai_audio = openai.OpenAI()

#     stt = STT(openai_client=openai_audio)

#     stt.listen_once_start()
#     sleep(5)
#     stt.listen_once_end()

#     stt.listen_continuous()

#     while True:
#         sleep(0.25)
#         while not stt.resultQueue.empty():
#             result = stt.resultQueue.get()
#             print(result)

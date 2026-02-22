"""
Full Voice Bot Pipeline: STT -> LLM -> TTS
Real-time voice conversation with F5-TTS Russian
"""
import os
import sys
import time
import torch
import numpy as np
import sounddevice as sd
import soundfile as sf
import ollama
import threading
import queue
import re
from pathlib import Path
from dataclasses import dataclass

# Preload cuDNN for faster-whisper GPU support
import ctypes
CUDNN_PATH = Path(__file__).parent / "venv/lib/python3.11/site-packages/nvidia/cudnn/lib"
if CUDNN_PATH.exists():
    for lib in ["libcudnn_ops.so.9", "libcudnn_cnn.so.9", "libcudnn_adv.so.9",
                "libcudnn_graph.so.9", "libcudnn_engines_runtime_compiled.so.9",
                "libcudnn_engines_precompiled.so.9", "libcudnn_heuristic.so.9", "libcudnn.so.9"]:
        lib_path = CUDNN_PATH / lib
        if lib_path.exists():
            try:
                ctypes.CDLL(str(lib_path), mode=ctypes.RTLD_GLOBAL)
            except OSError:
                pass

from faster_whisper import WhisperModel
from f5_tts.api import F5TTS
from ruaccent import RUAccent
from num2words import num2words


SAMPLE_RATE = 16000
VOICE_BOT_DIR = Path(__file__).parent
AUDIO_DIR = VOICE_BOT_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)

# F5-TTS Russian model path
F5TTS_MODEL_PATH = VOICE_BOT_DIR / "checkpoints" / "F5TTS_v1_Base_v2" / "model_last_inference.safetensors"
F5TTS_REF_AUDIO = VOICE_BOT_DIR / "audio" / "reference_voice.wav"


@dataclass
class PipelineMetrics:
    """Timing metrics for the pipeline"""
    stt_time: float = 0.0
    llm_time: float = 0.0
    llm_first_token: float = 0.0
    accent_time: float = 0.0
    tts_time: float = 0.0
    total_time: float = 0.0
    audio_input_duration: float = 0.0
    audio_output_duration: float = 0.0

    def print_summary(self):
        print("\n" + "=" * 60)
        print("Pipeline Metrics")
        print("=" * 60)
        print(f"STT time:           {self.stt_time:.2f}s")
        print(f"LLM first token:    {self.llm_first_token:.2f}s")
        print(f"LLM total time:     {self.llm_time:.2f}s")
        print(f"Accent time:        {self.accent_time*1000:.1f}ms")
        print(f"TTS time:           {self.tts_time:.2f}s")
        print("-" * 60)
        print(f"Total pipeline:     {self.total_time:.2f}s")
        print(f"Input audio:        {self.audio_input_duration:.2f}s")
        print(f"Output audio:       {self.audio_output_duration:.2f}s")
        print(f"Latency (to speech): {self.stt_time + self.llm_time + self.tts_time:.2f}s")


class VoicePipeline:
    """Full voice conversation pipeline with F5-TTS Russian"""

    def __init__(
        self,
        whisper_model: str = "large-v3-turbo",
        llm_model: str = "ministral-3:14b-instruct-2512-q8_0",
        device: str = None,
        use_streaming: bool = False,
    ):
        self.llm_model = llm_model
        self.use_streaming = use_streaming

        # Auto-detect device
        if device is None:
            self.device = "cuda" if torch.cuda.is_available() else "cpu"
        else:
            self.device = device

        print("=" * 60)
        print("Initializing Voice Pipeline (F5-TTS Russian)")
        print("=" * 60)
        print(f"Device: {self.device}")

        # Initialize STT on GPU
        print("\nLoading Whisper model...")
        stt_start = time.time()
        self.stt = WhisperModel(
            whisper_model,
            device=self.device,
            compute_type="float16" if self.device == "cuda" else "int8"
        )
        print(f"   Whisper loaded in {time.time() - stt_start:.2f}s (device: {self.device})")

        # Initialize F5-TTS with Russian model
        print("\nLoading F5-TTS Russian model...")
        tts_start = time.time()

        self.tts = F5TTS(
            model="F5TTS_v1_Base",
            ckpt_file=str(F5TTS_MODEL_PATH),
            device=self.device,
        )
        self.tts_sample_rate = self.tts.target_sample_rate

        # Compile model for faster inference (first run will be slow)
        self._compile_mode = None
        if self.device == "cuda":
            # Try max-autotune-no-cudagraphs first (best for DiT models)
            # Falls back to reduce-overhead if issues arise
            for compile_mode in ["max-autotune-no-cudagraphs", "reduce-overhead"]:
                try:
                    self.tts.ema_model = torch.compile(
                        self.tts.ema_model,
                        mode=compile_mode,
                        dynamic=False,  # Static shapes for better optimization
                    )
                    self._compile_mode = compile_mode
                    print(f"   F5-TTS loaded and compiled in {time.time() - tts_start:.2f}s")
                    print(f"   Compile mode: {compile_mode}")
                    break
                except Exception as e:
                    if compile_mode == "reduce-overhead":
                        print(f"   F5-TTS loaded in {time.time() - tts_start:.2f}s (compile failed: {e})")
                    continue
        else:
            print(f"   F5-TTS loaded in {time.time() - tts_start:.2f}s")
        print(f"   Sample rate: {self.tts_sample_rate}Hz")

        # Reference audio for voice cloning
        self.ref_audio = None
        self.ref_text = "Покупатели видят свои покупки и итоговую сумму, а также вашу рекламу. Экономия на чековой ленте. Чек можно просто сфотографировать на телефон. Вам не нужно покупать принтер чеков"
        if F5TTS_REF_AUDIO.exists():
            print(f"   Reference audio: {F5TTS_REF_AUDIO.name}")
            self.ref_audio = str(F5TTS_REF_AUDIO)

        # System prompt
        self.system_prompt = """Ты голосовой ассистент. СТРОГО отвечай ТОЛЬКО на русском языке.
Отвечай кратко и естественно, как в разговоре.
Избегай длинных списков и сложных конструкций. Говори просто и понятно.
Отвечай максимум 2-3 предложениями.

КРИТИЧЕСКИ ВАЖНО:
- НИКОГДА не используй английские слова - переводи их на русский
- НИКОГДА не используй китайские иероглифы
- НИКОГДА не используй латиницу
- Все технические термины пиши по-русски или транслитерируй кириллицей"""

        print(f"   Streaming TTS: {'enabled' if self.use_streaming else 'disabled'}")

        # Initialize RUAccent for stress marks
        print("\nLoading RUAccent (stress marks)...")
        accent_start = time.time()
        self.accentizer = RUAccent()
        # Custom dictionary for stress corrections
        custom_stress = {
            "готов": "гот+ов",
            "готова": "гот+ова",
            "готово": "гот+ово",
            "готовы": "гот+овы",
        }
        self.accentizer.load(omograph_model_size='turbo', use_dictionary=True, custom_dict=custom_stress)
        print(f"   RUAccent loaded in {time.time() - accent_start:.2f}s")

        print("\nPipeline ready!")

    def record_audio(self, duration: float = 5.0) -> np.ndarray:
        """Record audio from microphone"""
        print(f"\nRecording ({duration}s)... Speak now!")
        audio = sd.rec(
            int(duration * SAMPLE_RATE),
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype=np.float32
        )
        sd.wait()
        print("Recording complete")
        return audio.flatten()

    def speech_to_text(self, audio: np.ndarray) -> tuple[str, float]:
        """Convert speech to text"""
        temp_path = AUDIO_DIR / "temp_input.wav"
        sf.write(temp_path, audio, SAMPLE_RATE)

        start = time.time()
        segments, _ = self.stt.transcribe(
            str(temp_path),
            language="ru",
            beam_size=5,
            vad_filter=True
        )
        text = " ".join([s.text for s in segments]).strip()
        elapsed = time.time() - start

        return text, elapsed

    def filter_foreign_text(self, text: str) -> str:
        """Remove or transliterate foreign characters for TTS"""
        # Remove Chinese/Japanese/Korean characters
        text = re.sub(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]+', '', text)

        # Simple English to Russian transliteration for common words
        translit_map = {
            'a': 'а', 'b': 'б', 'c': 'с', 'd': 'д', 'e': 'е', 'f': 'ф',
            'g': 'г', 'h': 'х', 'i': 'и', 'j': 'дж', 'k': 'к', 'l': 'л',
            'm': 'м', 'n': 'н', 'o': 'о', 'p': 'п', 'q': 'к', 'r': 'р',
            's': 'с', 't': 'т', 'u': 'у', 'v': 'в', 'w': 'в', 'x': 'кс',
            'y': 'й', 'z': 'з',
        }

        def transliterate(match):
            word = match.group(0).lower()
            result = ''
            for char in word:
                result += translit_map.get(char, char)
            return result

        # Transliterate Latin words to Cyrillic
        text = re.sub(r'[a-zA-Z]+', transliterate, text)

        # Clean up extra spaces
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def numbers_to_words(self, text: str) -> str:
        """Convert numbers to Russian words for TTS"""
        def replace_number(match):
            num_str = match.group(0)
            try:
                # Handle decimals
                if '.' in num_str or ',' in num_str:
                    num_str = num_str.replace(',', '.')
                    return num2words(float(num_str), lang='ru')
                else:
                    return num2words(int(num_str), lang='ru')
            except:
                return num_str

        # Match integers and decimals
        return re.sub(r'\d+[.,]?\d*', replace_number, text)

    def add_stress_marks(self, text: str) -> str:
        """Add stress marks to Russian text using RUAccent"""
        try:
            return self.accentizer.process_all(text)
        except Exception as e:
            print(f"RUAccent error: {e}")
            return text

    def text_to_speech(self, text: str) -> tuple[np.ndarray, int, float, float]:
        """Convert text to speech using F5-TTS Russian
        Returns: (audio_data, sample_rate, tts_time, accent_time)
        """
        output_path = AUDIO_DIR / "temp_output.wav"

        # Filter foreign text, convert numbers, add stress marks
        accent_start = time.time()
        text_filtered = self.filter_foreign_text(text)
        text_with_words = self.numbers_to_words(text_filtered)
        text_with_stress = self.add_stress_marks(text_with_words)
        # Add trailing punctuation if missing
        if text_with_stress and text_with_stress[-1] not in '.!?':
            text_with_stress += '.'
        accent_time = time.time() - accent_start

        start = time.time()

        try:
            # Generate speech with F5-TTS
            # Using default parameters for best quality
            audio_data, sample_rate, _ = self.tts.infer(
                ref_file=self.ref_audio,
                ref_text=self.ref_text,
                gen_text=text_with_stress,
                file_wave=str(output_path),
                show_info=lambda x: None,  # Suppress progress output
                nfe_step=32,  # Default, best quality
                cfg_strength=2.5,  # Higher for more expressive output
                sway_sampling_coef=-1.0,  # Enable sway sampling for better quality
                cross_fade_duration=0.15,  # Smooth transitions between segments
                speed=1.0,  # Natural speed
                seed=281499361696202514,  # Best seed from search
            )

            # Add silence padding at the end to prevent cutoff (0.3 seconds)
            silence_samples = int(sample_rate * 0.3)
            silence = np.zeros(silence_samples, dtype=audio_data.dtype)
            audio_data = np.concatenate([audio_data, silence])

            elapsed = time.time() - start
            return audio_data, sample_rate, elapsed, accent_time

        except Exception as e:
            print(f"TTS Error: {e}")
            elapsed = time.time() - start
            return np.zeros(1000), self.tts_sample_rate, elapsed, accent_time

    def play_audio(self, audio: np.ndarray, sample_rate: int = 24000):
        """Play audio"""
        sd.play(audio, sample_rate)
        sd.wait()

    def _tts_worker(self, text_queue: queue.Queue, audio_queue: queue.Queue):
        """Worker thread for TTS synthesis"""
        while True:
            text = text_queue.get()
            if text is None:  # Poison pill
                audio_queue.put(None)
                break
            if text.strip():
                audio, sr, _, _ = self.text_to_speech(text)
                audio_queue.put((audio, sr))
            text_queue.task_done()

    def _audio_player(self, audio_queue: queue.Queue):
        """Worker thread for audio playback"""
        while True:
            item = audio_queue.get()
            if item is None:  # Poison pill
                break
            audio, sr = item
            sd.play(audio, sr)
            sd.wait()
            audio_queue.task_done()

    def run_conversation(self, record_duration: float = 5.0) -> PipelineMetrics:
        """Run conversation pipeline"""
        metrics = PipelineMetrics()
        pipeline_start = time.time()

        # Step 1: Record
        audio_input = self.record_audio(record_duration)
        metrics.audio_input_duration = record_duration

        # Step 2: STT
        print("\nTranscribing...")
        user_text, stt_time = self.speech_to_text(audio_input)
        metrics.stt_time = stt_time
        print(f"You said: {user_text}")

        if not user_text.strip():
            print("No speech detected")
            return metrics

        if self.use_streaming:
            return self._run_streaming(metrics, user_text, pipeline_start)
        else:
            return self._run_sequential(metrics, user_text, pipeline_start)

    def _run_sequential(self, metrics: PipelineMetrics, user_text: str, pipeline_start: float) -> PipelineMetrics:
        """Sequential mode: LLM completes, then TTS"""
        # Step 3: LLM
        print("\nAssistant: ", end="", flush=True)
        llm_start = time.time()
        first_token_time = None
        full_response = ""

        stream = ollama.chat(
            model=self.llm_model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_text}
            ],
            stream=True,
            think=False
        )

        for chunk in stream:
            if first_token_time is None:
                first_token_time = time.time() - llm_start
            content = chunk["message"]["content"]
            full_response += content
            print(content, end="", flush=True)

        print()
        metrics.llm_time = time.time() - llm_start
        metrics.llm_first_token = first_token_time or 0

        # Step 4: TTS (after LLM completes)
        tts_start = time.time()
        audio, sr, _, accent_time = self.text_to_speech(full_response)
        metrics.tts_time = time.time() - tts_start
        metrics.accent_time = accent_time

        # Step 5: Play
        self.play_audio(audio, sr)

        metrics.audio_output_duration = len(audio) / sr
        metrics.total_time = time.time() - pipeline_start
        return metrics

    def _run_streaming(self, metrics: PipelineMetrics, user_text: str, pipeline_start: float) -> PipelineMetrics:
        """Streaming mode: TTS starts while LLM generates"""
        # Setup streaming TTS pipeline
        text_queue = queue.Queue()
        audio_queue = queue.Queue()

        tts_thread = threading.Thread(target=self._tts_worker, args=(text_queue, audio_queue))
        player_thread = threading.Thread(target=self._audio_player, args=(audio_queue,))
        tts_thread.start()
        player_thread.start()

        # Step 3: LLM with streaming TTS
        print("\nAssistant: ", end="", flush=True)
        llm_start = time.time()
        first_token_time = None
        first_tts_sent = False
        full_response = ""
        current_sentence = ""

        stream = ollama.chat(
            model=self.llm_model,
            messages=[
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": user_text}
            ],
            stream=True,
            think=False
        )

        for chunk in stream:
            if first_token_time is None:
                first_token_time = time.time() - llm_start
            content = chunk["message"]["content"]
            full_response += content
            current_sentence += content
            print(content, end="", flush=True)

            # Check for sentence boundary
            if re.search(r'[.!?]\s*$', current_sentence) or len(current_sentence) > 100:
                if current_sentence.strip():
                    text_queue.put(current_sentence.strip())
                    if not first_tts_sent:
                        first_tts_sent = True
                        metrics.llm_first_token = first_token_time or 0
                current_sentence = ""

        # Send remaining text
        if current_sentence.strip():
            text_queue.put(current_sentence.strip())

        print()
        metrics.llm_time = time.time() - llm_start

        # Signal TTS to finish
        text_queue.put(None)

        # Wait for all audio to finish playing
        tts_thread.join()
        player_thread.join()

        metrics.tts_time = time.time() - llm_start - metrics.llm_time
        metrics.audio_output_duration = len(full_response) / 15  # Approximate
        metrics.total_time = time.time() - pipeline_start
        return metrics


def main():
    """Interactive voice bot"""
    print("\n" + "=" * 60)
    print("Voice Bot Pipeline (F5-TTS Russian)")
    print("=" * 60)

    # Initialize pipeline
    pipeline = VoicePipeline(
        whisper_model="large-v3-turbo",
        llm_model="ministral-3:14b-instruct-2512-q8_0",
    )

    # Startup greeting text (50 words)
    startup_text = """Добрый день! Я ваш голосовой помощник для работы с системой управления продажами.
Я могу помочь вам с информацией о товарах, клиентах и заказах. Задавайте любые вопросы
о функциях системы, аналитике продаж или технической поддержке. Готов ответить на ваши
вопросы и помочь в работе с си эр эм системой."""

    print("\n" + "=" * 60)
    print("Playing startup greeting...")
    print("=" * 60)
    print(f"\nGreeting: {startup_text}\n")

    # Synthesize and play startup greeting
    audio, sr, tts_time, _ = pipeline.text_to_speech(startup_text)
    print(f"TTS time: {tts_time:.2f}s, Audio duration: {len(audio)/sr:.2f}s")
    pipeline.play_audio(audio, sr)

    print("\n" + "=" * 60)
    print("Ready for conversation!")
    print("   Press Enter to start recording (5 seconds)")
    print("   Type 'q' to quit")
    print("=" * 60)

    while True:
        user_input = input("\nPress Enter to speak (or 'q' to quit): ")
        if user_input.lower() == 'q':
            print("Goodbye!")
            break

        metrics = pipeline.run_conversation(record_duration=5.0)
        metrics.print_summary()


if __name__ == "__main__":
    main()

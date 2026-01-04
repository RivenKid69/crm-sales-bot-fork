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
        llm_model: str = "qwen3:8b-fast",
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
        self.ref_text = "говно не смотрю уже очень давно я без понятия там уже сезона этак третьего чисто контент для говноедов я второй еле досмотрел еле-еле"
        if F5TTS_REF_AUDIO.exists():
            print(f"   Reference audio: {F5TTS_REF_AUDIO.name}")
            self.ref_audio = str(F5TTS_REF_AUDIO)

        # System prompt
        self.system_prompt = """Ты голосовой ассистент. ВСЕГДА отвечай ТОЛЬКО на русском языке.
Отвечай кратко и естественно, как в разговоре.
Избегай длинных списков и сложных конструкций. Говори просто и понятно.
Отвечай максимум 2-3 предложениями. Никогда не используй другие языки кроме русского."""

        print(f"   Streaming TTS: {'enabled' if self.use_streaming else 'disabled'}")
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

    def text_to_speech(self, text: str) -> tuple[np.ndarray, int, float]:
        """Convert text to speech using F5-TTS Russian"""
        output_path = AUDIO_DIR / "temp_output.wav"

        start = time.time()

        try:
            # Generate speech with F5-TTS
            # nfe_step=16 activates EPSS (Empirically Pruned Step Sampling)
            # which gives ~2x speedup with minimal quality loss
            audio_data, sample_rate, _ = self.tts.infer(
                ref_file=self.ref_audio,
                ref_text=self.ref_text,
                gen_text=text,
                file_wave=str(output_path),
                show_info=lambda x: None,  # Suppress progress output
                nfe_step=16,  # EPSS-optimized (was 32, now 2x faster)
                cfg_strength=1.7,  # Lower = more expressive (default 2.0)
                sway_sampling_coef=-1.0,  # Enable sway sampling for better quality
                speed=0.85,  # Slower, clearer pronunciation
            )

            elapsed = time.time() - start
            return audio_data, sample_rate, elapsed

        except Exception as e:
            print(f"TTS Error: {e}")
            elapsed = time.time() - start
            return np.zeros(1000), self.tts_sample_rate, elapsed

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
                audio, sr, _ = self.text_to_speech(text)
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
        audio, sr, _ = self.text_to_speech(full_response)
        metrics.tts_time = time.time() - tts_start

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
        llm_model="qwen3:1.7b",
    )

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

"""
Full Voice Bot Pipeline: STT -> LLM -> TTS
Real-time voice conversation with OpenAudio S1-mini TTS
"""
import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""  # Force CPU mode

import sys
import time
import torch
import numpy as np
import sounddevice as sd
import soundfile as sf
import ollama
from pathlib import Path
from dataclasses import dataclass

# Setup paths
VOICE_BOT_DIR = Path(__file__).parent
sys.path.insert(0, str(VOICE_BOT_DIR / "fish-speech"))

from faster_whisper import WhisperModel

# Fish Speech / OpenAudio imports
from fish_speech.inference_engine import TTSInferenceEngine
from fish_speech.models.dac.inference import load_model as load_decoder_model
from fish_speech.models.text2semantic.inference import launch_thread_safe_queue
from fish_speech.utils.schema import ServeTTSRequest, ServeReferenceAudio
from fish_speech.utils.file import audio_to_bytes, read_ref_text


SAMPLE_RATE = 16000
AUDIO_DIR = VOICE_BOT_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)

# OpenAudio S1-mini paths
OPENAUDIO_MODEL_DIR = VOICE_BOT_DIR / "checkpoints" / "openaudio-s1-mini"
OPENAUDIO_REF_AUDIO = VOICE_BOT_DIR / "audio" / "reference_ru_female.wav"


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
    """Full voice conversation pipeline with OpenAudio S1-mini TTS"""

    def __init__(
        self,
        whisper_model: str = "large-v3-turbo",
        llm_model: str = "qwen3:8b-fast",
    ):
        self.llm_model = llm_model
        self.device = "cpu"
        self.precision = torch.bfloat16

        print("=" * 60)
        print("Initializing Voice Pipeline (OpenAudio S1-mini)")
        print("=" * 60)

        # Initialize STT
        print("\nLoading Whisper model...")
        stt_start = time.time()
        self.stt = WhisperModel(
            whisper_model,
            device="cpu",
            compute_type="int8"
        )
        print(f"   Whisper loaded in {time.time() - stt_start:.2f}s")

        # Initialize OpenAudio S1-mini TTS
        print("\nLoading OpenAudio S1-mini model...")
        tts_start = time.time()

        # Load LLAMA model (text to semantic)
        print("   Loading LLAMA model...")
        self.llama_queue = launch_thread_safe_queue(
            checkpoint_path=str(OPENAUDIO_MODEL_DIR),  # Directory path
            device=self.device,
            precision=self.precision,
            compile=False,
        )

        # Load decoder model (DAC)
        print("   Loading decoder model...")
        self.decoder_model = load_decoder_model(
            config_name="modded_dac_vq",
            checkpoint_path=str(OPENAUDIO_MODEL_DIR / "codec.pth"),
            device=self.device,
        )

        # Create TTS engine
        self.tts_engine = TTSInferenceEngine(
            llama_queue=self.llama_queue,
            decoder_model=self.decoder_model,
            precision=self.precision,
            compile=False,
        )

        # Get sample rate from decoder
        if hasattr(self.decoder_model, "spec_transform"):
            self.tts_sample_rate = self.decoder_model.spec_transform.sample_rate
        else:
            self.tts_sample_rate = self.decoder_model.sample_rate

        print(f"   OpenAudio loaded in {time.time() - tts_start:.2f}s")
        print(f"   Sample rate: {self.tts_sample_rate}Hz")

        # Load reference audio for voice cloning
        self.ref_audio_bytes = None
        self.ref_text = ""
        if OPENAUDIO_REF_AUDIO.exists():
            print(f"   Loading reference audio: {OPENAUDIO_REF_AUDIO.name}")
            self.ref_audio_bytes = audio_to_bytes(str(OPENAUDIO_REF_AUDIO))

        # System prompt
        self.system_prompt = """Ты голосовой ассистент. ВСЕГДА отвечай ТОЛЬКО на русском языке.
Отвечай кратко и естественно, как в разговоре.
Избегай длинных списков и сложных конструкций. Говори просто и понятно.
Отвечай максимум 2-3 предложениями. Никогда не используй другие языки кроме русского."""

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
        """Convert text to speech using OpenAudio S1-mini"""
        output_path = AUDIO_DIR / "temp_output.wav"

        start = time.time()

        # Prepare references for voice cloning
        references = []
        if self.ref_audio_bytes:
            references.append(
                ServeReferenceAudio(
                    audio=self.ref_audio_bytes,
                    text=self.ref_text
                )
            )

        # Create TTS request
        request = ServeTTSRequest(
            text=text,
            references=references,
            reference_id=None,
            max_new_tokens=1024,
            chunk_length=200,
            top_p=0.7,
            repetition_penalty=1.2,
            temperature=0.7,
            format="wav",
            streaming=False,
        )

        # Generate speech
        audio_data = None
        sample_rate = self.tts_sample_rate

        for result in self.tts_engine.inference(request):
            if result.code == "final":
                if isinstance(result.audio, tuple):
                    sample_rate, audio_data = result.audio
            elif result.code == "error":
                print(f"TTS Error: {result.error}")
                return np.zeros(1000), sample_rate, time.time() - start

        elapsed = time.time() - start

        if audio_data is None:
            print("No audio generated")
            return np.zeros(1000), sample_rate, elapsed

        # Save to file
        sf.write(output_path, audio_data, sample_rate)

        return audio_data, sample_rate, elapsed

    def play_audio(self, audio: np.ndarray, sample_rate: int = 24000):
        """Play audio"""
        sd.play(audio, sample_rate)
        sd.wait()

    def run_conversation(self, record_duration: float = 5.0) -> PipelineMetrics:
        """Run full conversation pipeline"""
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

        # Step 3: LLM (with streaming output)
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
        metrics.llm_first_token = first_token_time or 0
        metrics.llm_time = time.time() - llm_start

        # Step 4: TTS
        print("\nSynthesizing speech...")
        audio_output, sr, tts_time = self.text_to_speech(full_response)
        metrics.tts_time = tts_time
        metrics.audio_output_duration = len(audio_output) / sr

        # Step 5: Play
        print("Playing response...")
        self.play_audio(audio_output, sr)

        metrics.total_time = time.time() - pipeline_start
        return metrics


def main():
    """Interactive voice bot"""
    print("\n" + "=" * 60)
    print("Voice Bot Pipeline (OpenAudio S1-mini TTS)")
    print("=" * 60)

    # Initialize pipeline
    pipeline = VoicePipeline(
        whisper_model="large-v3-turbo",
        llm_model="qwen3:8b"
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

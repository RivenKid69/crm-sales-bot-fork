"""
Full Voice Bot Pipeline: STT -> LLM -> TTS
Real-time voice conversation with CosyVoice 3.0 TTS
"""
import sys
import time
import numpy as np
import sounddevice as sd
import soundfile as sf
import ollama
from pathlib import Path
from dataclasses import dataclass

# Add CosyVoice to path
VOICE_BOT_DIR = Path(__file__).parent
sys.path.insert(0, str(VOICE_BOT_DIR / "CosyVoice"))
sys.path.insert(0, str(VOICE_BOT_DIR / "CosyVoice" / "third_party" / "Matcha-TTS"))

from faster_whisper import WhisperModel
from cosyvoice.cli.cosyvoice import AutoModel
import torchaudio


SAMPLE_RATE = 16000
AUDIO_DIR = VOICE_BOT_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)

# CosyVoice paths
COSYVOICE_MODEL_DIR = VOICE_BOT_DIR / "CosyVoice" / "pretrained_models" / "Fun-CosyVoice3-0.5B"
COSYVOICE_REF_AUDIO = VOICE_BOT_DIR / "CosyVoice" / "asset" / "cross_lingual_prompt.wav"


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
    """Full voice conversation pipeline with CosyVoice 3.0 TTS"""

    def __init__(
        self,
        whisper_model: str = "large-v3-turbo",
        llm_model: str = "qwen3:8b",
    ):
        self.llm_model = llm_model

        print("=" * 60)
        print("Initializing Voice Pipeline")
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

        # Initialize CosyVoice TTS
        print("\nLoading CosyVoice 3.0 model...")
        tts_start = time.time()
        self.tts = AutoModel(model_dir=str(COSYVOICE_MODEL_DIR))
        self.tts_sample_rate = self.tts.sample_rate
        print(f"   CosyVoice loaded in {time.time() - tts_start:.2f}s")
        print(f"   Sample rate: {self.tts_sample_rate}Hz")

        # System prompt
        self.system_prompt = """Ты голосовой ассистент. ВСЕГДА отвечай ТОЛЬКО на русском языке.
Отвечай кратко и естественно, как в разговоре.
Избегай длинных списков и сложных конструкций. Говори просто и понятно.
Отвечай максимум 2-3 предложениями. Никогда не используй другие языки кроме русского."""

        # TTS prompt for Russian (slow speed)
        self.tts_prompt = "You are a helpful assistant. Говори по-русски медленно и чётко.<|endofprompt|>"

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
        """Convert text to speech using CosyVoice 3.0"""
        output_path = AUDIO_DIR / "temp_output.wav"

        start = time.time()

        # Generate speech with CosyVoice
        audio_tensor = None
        for output in self.tts.inference_instruct2(
            text,
            self.tts_prompt,
            str(COSYVOICE_REF_AUDIO),
            stream=False
        ):
            audio_tensor = output['tts_speech']

        # Save to file
        torchaudio.save(str(output_path), audio_tensor, self.tts_sample_rate)

        elapsed = time.time() - start

        # Load as numpy array
        audio, sr = sf.read(output_path)
        return audio, sr, elapsed

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
            stream=True
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
    print("Voice Bot Pipeline (CosyVoice 3.0 TTS)")
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

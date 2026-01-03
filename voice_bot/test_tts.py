"""
Test Text-to-Speech with XTTS-ru-ipa
Russian-optimized TTS using IPA transcription
"""
import time
import torch
import sounddevice as sd
import soundfile as sf
from pathlib import Path

from TTS.tts.configs.xtts_config import XttsConfig
from TTS.tts.models.xtts import Xtts
from omogre import Transcriptor

AUDIO_DIR = Path(__file__).parent / "audio"
AUDIO_DIR.mkdir(exist_ok=True)

MODEL_DIR = Path(__file__).parent / "models" / "xtts-ru-ipa"
REFERENCE_AUDIO = MODEL_DIR / "reference_audio.wav"


class XTTSRussian:
    """XTTS wrapper for Russian TTS with IPA transcription"""

    def __init__(self, model_path: Path = MODEL_DIR):
        print("📥 Loading XTTS-ru-ipa model...")
        start = time.time()

        # Get device
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        print(f"   Device: {self.device}")

        # Load config and model
        config = XttsConfig()
        config.load_json(str(model_path / "config.json"))

        self.model = Xtts.init_from_config(config)
        self.model.load_checkpoint(
            config,
            checkpoint_dir=str(model_path),
            checkpoint_path=str(model_path / "model.pth"),
            vocab_path=str(model_path / "vocab.json"),
            eval=True,
            use_deepspeed=False
        )
        self.model.to(self.device)

        # Load transcriptor for IPA
        print("   Loading IPA transcriptor...")
        self.transcriptor = Transcriptor()

        # Compute speaker latents from reference audio
        print("   Computing speaker latents...")
        self.gpt_cond_latent, self.speaker_embedding = self.model.get_conditioning_latents(
            audio_path=[str(REFERENCE_AUDIO)]
        )

        print(f"✅ Model loaded in {time.time() - start:.2f}s")

    def transcribe_to_ipa(self, text: str) -> str:
        """Convert Russian text to IPA"""
        return self.transcriptor([text])[0]

    def synthesize(self, text: str, output_path: Path = None) -> tuple:
        """Generate speech from Russian text"""
        # Convert to IPA
        ipa_text = self.transcribe_to_ipa(text)
        print(f"   IPA: {ipa_text}")

        start = time.time()

        # Generate audio
        out = self.model.inference(
            text=ipa_text,
            language="ru",
            gpt_cond_latent=self.gpt_cond_latent,
            speaker_embedding=self.speaker_embedding,
            temperature=0.7,
            enable_text_splitting=True
        )

        audio = out["wav"]
        sample_rate = 24000  # XTTS default

        elapsed = time.time() - start

        if output_path:
            sf.write(output_path, audio, sample_rate)

        return audio, sample_rate, elapsed


def play_audio(audio, sample_rate: int):
    """Play audio"""
    print("🔊 Playing...")
    sd.play(audio, sample_rate)
    sd.wait()


def test_tts():
    """Main test function"""
    print("=" * 50)
    print("🔊 TTS Test (XTTS-ru-ipa)")
    print("=" * 50)

    # Initialize
    tts = XTTSRussian()

    # Test texts
    texts = [
        "Привет! Я голосовой ассистент.",
        "Искусственный интеллект помогает решать сложные задачи.",
        "Сегодня хорошая погода для прогулки.",
    ]

    results = []

    for i, text in enumerate(texts):
        print(f"\n📝 Text {i+1}: {text}")
        print("🔄 Synthesizing...")

        output_path = AUDIO_DIR / f"xtts_test_{i+1}.wav"
        audio, sr, elapsed = tts.synthesize(text, output_path)

        duration = len(audio) / sr

        print(f"✅ Generated in {elapsed:.2f}s")
        print(f"📈 Audio duration: {duration:.2f}s")
        print(f"🚀 Real-time factor: {elapsed / duration:.2f}x")

        results.append({
            "text": text,
            "synthesis_time": elapsed,
            "audio_duration": duration,
            "rtf": elapsed / duration
        })

        # Play audio
        play_audio(audio, sr)

    # Summary
    print("\n" + "=" * 50)
    print("📊 Summary:")
    print("=" * 50)

    avg_rtf = sum(r["rtf"] for r in results) / len(results)
    print(f"🚀 Average RTF: {avg_rtf:.2f}x")

    if avg_rtf < 1.0:
        print("✅ TTS is faster than real-time!")
    else:
        print("⚠️  TTS is slower than real-time (consider GPU)")

    return results


if __name__ == "__main__":
    test_tts()

"""
Voice input engine — microphone recording + whisper transcription.

Supports push-to-talk via arecord (ALSA) or ffmpeg (PulseAudio/PipeWire),
then transcribes the recording with whisper-cli (C++ binary) or Python
openai-whisper as a fallback.

Usage:
    from engine.voice import VoiceEngine

    engine = VoiceEngine(config)
    engine.toggle()        # start/stop recording
    text = engine.last_transcript
"""

import logging
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ─── Recording ─────────────────────────────────────────────────────


class VoiceRecorder:
    """Capture 16 kHz mono WAV from the default microphone."""

    def __init__(self, config: dict):
        voice_cfg = config.get("voice", {})
        self.sample_rate: int = 16000
        self.channels: int = 1
        self.silence_threshold: float = voice_cfg.get("silence_threshold", 2.0)
        self.max_duration: int = voice_cfg.get("max_duration", 30)
        self._process: Optional[subprocess.Popen] = None
        self._wav_path: Optional[str] = None
        self._recorder: Optional[str] = None  # lazy-detected
        self._started_at: float = 0.0

    # ── Detect available recorder binary ───────────────────────────

    @staticmethod
    def _detect_recorder() -> Optional[str]:
        """Return the best available recording command, or None."""
        for cmd in ["arecord", "ffmpeg", "sox"]:
            if shutil.which(cmd):
                return cmd
        return None

    # ── Start recording ────────────────────────────────────────────

    def start(self) -> str:
        """Start recording. Returns the WAV output path."""
        if self._process and self._process.poll() is None:
            raise RuntimeError("Already recording")

        if self._recorder is None:
            self._recorder = self._detect_recorder()
        if self._recorder is None:
            raise RuntimeError(
                "No recorder found. Install alsa-utils (arecord), ffmpeg, or sox."
            )

        tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        self._wav_path = tmp.name
        tmp.close()

        cmd = self._build_cmd(self._wav_path)
        logger.debug("[voice] recording cmd: %s", cmd)
        self._process = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        self._started_at = time.time()
        return self._wav_path

    def _build_cmd(self, wav_path: str) -> list:
        if self._recorder == "arecord":
            return [
                "arecord",
                "-q",
                "-f", "S16_LE",
                "-r", str(self.sample_rate),
                "-c", str(self.channels),
                "-d", str(self.max_duration),
                wav_path,
            ]
        if self._recorder == "ffmpeg":
            return [
                "ffmpeg",
                "-y",
                "-f", "pulse", "-i", "default",
                "-ar", str(self.sample_rate),
                "-ac", str(self.channels),
                "-sample_fmt", "s16",
                "-t", str(self.max_duration),
                wav_path,
            ]
        # sox fallback (rec command)
        return [
            "rec",
            "-q",
            "-r", str(self.sample_rate),
            "-c", str(self.channels),
            "-b", "16",
            wav_path,
        ]

    # ── Stop recording ─────────────────────────────────────────────

    def stop(self) -> Optional[str]:
        """Stop recording. Returns the WAV path, or None if not recording."""
        if self._process is None:
            return None

        wav_path = self._wav_path
        elapsed = time.time() - self._started_at

        # Graceful terminate, then kill after 2s
        try:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=2)
        except Exception as exc:
            logger.warning("[voice] stop error: %s", exc)

        self._process = None
        if wav_path and Path(wav_path).exists() and Path(wav_path).stat().st_size > 44:
            logger.debug("[voice] recorded %.1fs to %s", elapsed, wav_path)
            return wav_path

        # Empty or missing file — clean up
        if wav_path and Path(wav_path).exists():
            Path(wav_path).unlink(missing_ok=True)
        return None

    @property
    def is_recording(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def cleanup(self, wav_path: str) -> None:
        """Remove a temporary WAV file."""
        Path(wav_path).unlink(missing_ok=True)


# ─── Transcription ─────────────────────────────────────────────────


class WhisperTranscriber:
    """Transcribe WAV files using whisper-cli (C++) or Python whisper (openai-whisper)."""

    def __init__(self, config: dict):
        voice_cfg = config.get("voice", {})
        self.whisper_bin: str = voice_cfg.get("whisper_bin", "whisper-cli")
        self.model_path: str = voice_cfg.get(
            "model", "models/ggml-base.en.bin"
        )
        self.language: str = voice_cfg.get("language", "en")
        self._backend: Optional[str] = None  # "cpp" or "python", lazy-detected

    def _detect_backend(self) -> Optional[str]:
        """Return 'python' if openai-whisper is importable, 'cpp' if whisper-cli is usable, else None."""
        # Try Python openai-whisper first (in-process, faster after first load)
        try:
            import whisper  # noqa: F401
            return "python"
        except ImportError:
            pass
        # Fall back to C++ whisper-cli
        if shutil.which(self.whisper_bin) or Path(self.whisper_bin).is_file():
            if Path(self.model_path).is_file():
                return "cpp"
        return None

    def is_available(self) -> bool:
        """Check if any whisper backend is present."""
        return self._detect_backend() is not None

    def transcribe(self, wav_path: str) -> Optional[str]:
        """Run whisper on a WAV file. Returns transcript text, or None."""
        backend = self._detect_backend()
        if backend is None:
            return None
        self._backend = backend

        if backend == "cpp":
            return self._transcribe_cpp(wav_path)
        return self._transcribe_python(wav_path)

    def _transcribe_cpp(self, wav_path: str) -> Optional[str]:
        """Transcribe using whisper-cli (C++ binary)."""
        cmd = [
            self.whisper_bin,
            "-m", self.model_path,
            "-f", wav_path,
            "--no-timestamps",
            "-nt",
            "--language", self.language,
        ]
        logger.debug("[voice] whisper-cpp cmd: %s", cmd)
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        except FileNotFoundError:
            logger.error("[voice] whisper-cli not found at: %s", self.whisper_bin)
            return None
        except subprocess.TimeoutExpired:
            logger.error("[voice] whisper-cli timed out")
            return None

        if result.returncode != 0:
            stderr = result.stderr.strip()[:300]
            logger.error("[voice] whisper error: %s", stderr)
            return None

        lines = result.stdout.strip().splitlines()
        text_lines = [
            l.strip()
            for l in lines
            if l.strip() and l.strip() != "[BLANK_AUDIO]"
        ]
        transcript = " ".join(text_lines).strip()
        return transcript or None

    def _transcribe_python(self, wav_path: str) -> Optional[str]:
        """Transcribe using openai-whisper Python API (in-process, model stays loaded)."""
        try:
            import whisper as _whisper
        except ImportError:
            logger.error("[voice] openai-whisper not installed — pip install openai-whisper")
            return None

        model_name = "base" if self.language == "en" else "base"
        try:
            model = _whisper.load_model(model_name)
            result = model.transcribe(
                wav_path,
                language=self.language if self.language != "auto" else None,
                fp16=False,
            )
            text = result.get("text", "").strip()
            return text or None
        except Exception as exc:
            logger.error("[voice] whisper Python error: %s", exc)
            return None


# ─── Orchestrator ───────────────────────────────────────────────────


# ─── TTS (Text-to-Speech) ──────────────────────────────────────────


class VoiceSpeaker:
    """Speak text aloud — Piper (neural, human-sounding) as primary, espeak-ng as fallback."""

    # Voice presets: gender → (piper_model, espeak_voice)
    VOICE_PRESETS = {
        "female": ("en_US-lessac-medium", "en-us"),
        "male": ("en_US-joe-medium", "en-us+m3"),
    }

    def __init__(self, config: dict):
        voice_cfg = config.get("voice", {})
        self.enabled: bool = voice_cfg.get("tts", True)
        self.rate: int = voice_cfg.get("tts_rate", 160)
        self.gender: str = voice_cfg.get("tts_gender", "female")
        self.piper_model: str = voice_cfg.get("tts_voice", self.VOICE_PRESETS.get(self.gender, self.VOICE_PRESETS["female"])[0])
        self.espeak_voice: str = voice_cfg.get("tts_espeak_voice", self.VOICE_PRESETS.get(self.gender, self.VOICE_PRESETS["female"])[1])
        self._backend: Optional[str] = None
        self._piper_process: Optional[Any] = None
        self._process: Optional[subprocess.Popen] = None
        self._detect_backend()

    def set_gender(self, gender: str) -> bool:
        """Switch voice gender. Returns True if preset exists."""
        gender = gender.lower()
        if gender not in self.VOICE_PRESETS:
            return False
        self.gender = gender
        self.piper_model, self.espeak_voice = self.VOICE_PRESETS[gender]
        return True

    def _detect_backend(self) -> None:
        """Pick Piper (neural TTS) first, fall back to espeak-ng."""
        # Try Piper — neural TTS, sounds human
        try:
            import piper  # noqa: F401
            self._backend = "piper"
            logger.info("TTS backend: piper (neural)")
            return
        except ImportError:
            pass
        # Fallback: espeak-ng
        for cmd in ["espeak-ng", "espeak"]:
            if shutil.which(cmd):
                self._backend = cmd
                logger.info("TTS backend: %s (fallback)", cmd)
                return
        logger.warning("No TTS engine found — pip install piper-tts or apt install espeak-ng")

    def is_available(self) -> bool:
        return self._backend is not None

    def speak(self, text: str) -> None:
        """Speak *text* aloud (non-blocking)."""
        if not self.enabled or not self._backend or not text.strip():
            return
        clean = self._clean_text(text)
        if not clean.strip():
            return
        try:
            if self._backend == "piper":
                self._speak_piper(clean)
            elif self._backend in ("espeak-ng", "espeak"):
                cmd = [self._backend, "-v", self.espeak_voice, "-s", str(self.rate), clean]
                self._process = subprocess.Popen(
                    cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
        except Exception as exc:
            logger.debug("TTS error: %s", exc)

    def _speak_piper(self, text: str) -> None:
        """Synthesize with Piper (neural TTS) and play via aplay."""
        try:
            from piper import PiperVoice
        except ImportError:
            return

        # Look for model in standard location
        model_name = self.piper_model  # e.g. "en_US-lessac-medium"
        model_path = os.path.expanduser(f"~/.local/share/piper/{model_name}.onnx")
        if not os.path.isfile(model_path):
            logger.warning("Piper model not found at %s — download from huggingface.co/rhasspy/piper-voices", model_path)
            return

        try:
            voice = PiperVoice.load(model_path)
            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        wav_path = tmp.name
        tmp.close()
            raw = b"".join(c.audio_int16_bytes for c in voice.synthesize(text))
            import wave
            with wave.open(wav_path, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(22050)
                wf.writeframes(raw)
            self._process = subprocess.Popen(
                ["aplay", "-q", wav_path],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        except Exception as exc:
            logger.debug("Piper synthesize error: %s", exc)

    def wait(self) -> None:
        """Block until current speech finishes."""
        if self._process and self._process.poll() is None:
            self._process.wait()

    def stop(self) -> None:
        """Kill any in-progress speech."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                self._process.kill()
        self._process = None

    @staticmethod
    def _clean_text(text: str) -> str:
        """Strip markdown, code, and /thinking blocks for cleaner speech."""
        import re
        # Strip /thinking blocks
        lines = text.split('\n')
        out_lines = []
        skip = False
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('/thinking'):
                # If there's content after /thinking on same line, just skip this line
                # Otherwise skip until blank line
                rest = stripped[len('/thinking'):].strip()
                if rest:
                    continue  # inline /thinking with text — just drop this line
                skip = True
                continue
            if skip:
                if stripped == '':
                    skip = False
                continue
            out_lines.append(line)
        out = '\n'.join(out_lines)
        out = re.sub(r"```[\s\S]*?```", "", out)
        out = re.sub(r"`[^`]+`", "", out)
        out = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", out)
        out = re.sub(r"[*_#>|~\-]{2,}", "", out)
        return out.strip()


class VoiceEngine:
    """
    High-level voice input: record → transcribe → return text.

    Usage in the terminal UI:
        v = VoiceEngine(config)
        v.start_recording()       # user holds key / toggles on
        ...
        text = v.stop_and_transcribe()  # user releases / toggles off
    """

    def __init__(self, config: dict):
        self.config = config
        voice_cfg = config.get("voice", {})
        self.enabled: bool = voice_cfg.get("enabled", False)
        self.push_to_talk: bool = voice_cfg.get("push_to_talk", True)

        self.recorder = VoiceRecorder(config)
        self.transcriber = WhisperTranscriber(config)
        self.speaker = VoiceSpeaker(config)

        self.last_transcript: Optional[str] = None
        self._last_wav: Optional[str] = None

    def is_available(self) -> bool:
        """True when a whisper backend (C++ or Python) is present."""
        return self.transcriber.is_available()

    @property
    def is_recording(self) -> bool:
        return self.recorder.is_recording

    def start_recording(self) -> None:
        """Begin microphone capture."""
        if not self.is_available():
            raise RuntimeError(
                "Voice not available — install whisper.cpp or openai-whisper"
            )
        self.recorder.start()

    def stop_and_transcribe(self) -> Optional[str]:
        """Stop recording and run whisper transcription."""
        wav_path = self.recorder.stop()
        if wav_path is None:
            return None

        try:
            text = self.transcriber.transcribe(wav_path)
        finally:
            self.recorder.cleanup(wav_path)

        self.last_transcript = text
        return text

    def cancel_recording(self) -> None:
        """Stop recording without transcribing."""
        wav_path = self.recorder.stop()
        if wav_path:
            self.recorder.cleanup(wav_path)

    def speak(self, text: str) -> None:
        """Speak text aloud via TTS (only when voice is enabled)."""
        if self.enabled:
            self.speaker.speak(text)

    def stop_speaking(self) -> None:
        """Interrupt current TTS playback."""
        self.speaker.stop()

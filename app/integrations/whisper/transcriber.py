import asyncio
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_model = None


def load_model(model_name: str = "small") -> None:
    global _model
    import whisper
    logger.info("Loading Whisper model '%s'…", model_name)
    _model = whisper.load_model(model_name)
    logger.info("Whisper model ready.")


async def transcribe(audio_path: Path) -> str:
    """Transcribe an audio file. Runs Whisper in a thread pool to avoid blocking."""
    if _model is None:
        from app.config import settings
        load_model(settings.whisper_model)

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,
        lambda: _model.transcribe(str(audio_path), language="it"),
    )
    return result["text"].strip()

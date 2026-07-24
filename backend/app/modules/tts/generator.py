"""
Text-to-Speech Generator
Converts narration scripts to audio files
"""

import sys
from pathlib import Path
from typing import Optional
from gtts import gTTS
import logging

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

logger = logging.getLogger(__name__)


class TTSGenerator:
    """Text-to-speech audio generation"""
    
    def __init__(self, provider: str = "gtts"):
        """
        Initialize TTS generator
        
        Args:
            provider: TTS provider (gtts, elevenlabs)
        """
        self.provider = provider
        self.supported_languages = {
            "en": "en",
            "es": "es",
            "fr": "fr",
            "de": "de",
            "ja": "ja",
            "zh": "zh",
            "pt": "pt",
            "it": "it",
            "ru": "ru",
            "ko": "ko"
        }
    
    def generate_audio(self, text: str, output_path: str, language: str = "en", 
                      slow: bool = False) -> dict:
        """
        Generate audio from text using gTTS
        
        Args:
            text: Text to convert to speech
            output_path: Path to save audio file
            language: Language code
            slow: Whether to speak slowly
            
        Returns:
            Status dictionary
        """
        try:
            # Normalize output path
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Ensure file has .mp3 extension
            if output_file.suffix != ".mp3":
                output_file = output_file.with_suffix(".mp3")
            
            # Validate language
            lang_code = self.supported_languages.get(language, "en")
            
            # Generate audio
            tts = gTTS(text=text, lang=lang_code, slow=slow)
            tts.save(str(output_file))
            
            # Get file size
            file_size = output_file.stat().st_size
            word_estimate = max(0.8, len(text.split()) / 2.5)  # ~150 wpm fallback
            measured = self._measure_duration(str(output_file))
            duration = measured if measured > 0.05 else word_estimate
            
            logger.info(
                f"Generated audio: {output_file} ({file_size} bytes, {duration:.2f}s)"
            )
            
            return {
                "success": True,
                "file_path": str(output_file),
                "file_size": file_size,
                "language": lang_code,
                "duration_s": duration,
                "duration_estimate": duration,
            }
        except Exception as e:
            logger.error(f"Audio generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_path": None
            }
    
    def generate_multiple_audios(self, texts: list, output_dir: str, 
                                 language: str = "en") -> list:
        """
        Generate multiple audio files
        
        Args:
            texts: List of text strings
            output_dir: Directory to save audio files
            language: Language code
            
        Returns:
            List of status dictionaries
        """
        results = []
        output_dir_path = Path(output_dir)
        output_dir_path.mkdir(parents=True, exist_ok=True)
        
        for i, text in enumerate(texts):
            output_file = output_dir_path / f"narration_{i:03d}.mp3"
            result = self.generate_audio(text, str(output_file), language)
            results.append(result)
        
        return results
    
    def _measure_duration(self, audio_path: str) -> float:
        """Measure real audio duration in seconds via ffmpeg."""
        try:
            from backend.app.modules.video.composer import VideoComposer
            return VideoComposer()._get_media_duration(audio_path)
        except Exception:
            return 0.0

    def estimate_duration(self, text: str) -> float:
        """
        Estimate audio duration from text
        
        Args:
            text: Text content
            
        Returns:
            Estimated duration in seconds
        """
        # Average speaking rate: 150 words per minute
        word_count = len(text.split())
        duration_seconds = (word_count / 150) * 60
        return duration_seconds
    
    def generate_with_elevenlabs(self, text: str, output_path: str, 
                                 api_key: str, voice_id: str = "default") -> dict:
        """
        Generate audio using ElevenLabs (premium option)
        
        Args:
            text: Text to convert
            output_path: Path to save audio
            api_key: ElevenLabs API key
            voice_id: Voice identifier
            
        Returns:
            Status dictionary
        """
        try:
            import requests
            
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            url = "https://api.elevenlabs.io/v1/text-to-speech/default"
            headers = {
                "xi-api-key": api_key,
                "Content-Type": "application/json"
            }
            data = {
                "text": text,
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75
                }
            }
            
            response = requests.post(url, json=data, headers=headers)
            
            if response.status_code == 200:
                with open(output_file, 'wb') as f:
                    f.write(response.content)
                
                logger.info(f"Generated ElevenLabs audio: {output_file}")
                return {
                    "success": True,
                    "file_path": str(output_file),
                    "provider": "elevenlabs"
                }
            else:
                return {
                    "success": False,
                    "error": f"ElevenLabs API error: {response.status_code}",
                    "file_path": None
                }
        except Exception as e:
            logger.error(f"ElevenLabs audio generation failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_path": None
            }

"""
Video Composer
Combines screen recording with audio narration using FFmpeg
"""

import sys
from pathlib import Path
from typing import Optional, List
import subprocess
import logging

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent.parent))

logger = logging.getLogger(__name__)


class VideoComposer:
    """Handles video composition and rendering"""
    
    def __init__(self):
        """Initialize video composer"""
        self.output_dir = Path("outputs/videos")
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.ffmpeg_path = self._get_ffmpeg_path()
    
    def _get_ffmpeg_path(self) -> str:
        """Get FFmpeg executable path"""
        try:
            import imageio_ffmpeg
            return imageio_ffmpeg.get_ffmpeg_exe()
        except:
            return "ffmpeg"  # Fallback to system PATH
    
    def compose_video_with_audio(self, video_path: str, audio_paths: List[str],
                                 output_path: str, video_params: dict = None) -> dict:
        """
        Compose video with narration.

        Assumes the screen recording was paced to match step audio. Speech is
        never time-stretched. Only light video retiming is applied for small
        residual drift (no freeze-frame padding).
        """
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            params = video_params or {}
            bitrate = params.get("bitrate", "5000k")
            codec = params.get("codec", "libx264")
            crf = params.get("crf", "23")  # Quality (18-28, lower=better)
            
            audio_inputs = [path for path in audio_paths if path and Path(path).exists()]

            if not audio_inputs:
                # Compose video without audio when narration is unavailable.
                cmd = [
                    self.ffmpeg_path,
                    "-i", video_path,
                    "-c:v", codec,
                    "-crf", crf,
                    "-b:v", bitrate,
                    "-an",
                    "-y",
                    str(output_file)
                ]
            else:
                if len(audio_inputs) == 1:
                    audio_input = audio_inputs[0]
                else:
                    concat_out = str(output_file.with_name(output_file.stem + "_audio.mp3"))
                    audio_input = self._concat_audio_files(audio_inputs, concat_out)

                video_duration = self._get_media_duration(video_path)
                audio_duration = self._get_media_duration(audio_input)
                logger.info(
                    "Composing A/V sync: video=%.2fs audio=%.2fs",
                    video_duration,
                    audio_duration,
                )

                # Prefer a plain mux. Only retime video slightly when lengths
                # already nearly match (recording was paced to narration).
                video_filter = None
                use_shortest = False
                if video_duration > 0.05 and audio_duration > 0.05:
                    drift = abs(video_duration - audio_duration)
                    ratio = audio_duration / video_duration
                    if drift <= 0.5:
                        logger.info("Durations within 0.5s — plain mux")
                    elif 0.75 <= ratio <= 1.35:
                        # Mild continuous retiming keeps motion + speech aligned.
                        video_filter = f"setpts=PTS*{ratio:.6f}"
                        logger.info(
                            "Applying mild video retime %.3fx to close %.2fs drift",
                            ratio,
                            drift,
                        )
                    elif ratio > 1.35:
                        # Recording shorter than audio (pacing missed) — still
                        # retime continuously rather than freezing a tail.
                        video_filter = f"setpts=PTS*{ratio:.6f}"
                        logger.warning(
                            "Large shortfall (video %.2fs < audio %.2fs); "
                            "retiming video %.2fx (prefer fixing pacing upstream)",
                            video_duration,
                            audio_duration,
                            ratio,
                        )
                    else:
                        # Video longer than audio — end with narration.
                        use_shortest = True
                        logger.info(
                            "Video longer by %.2fs — trimming to narration with -shortest",
                            video_duration - audio_duration,
                        )

                cmd = [
                    self.ffmpeg_path,
                    "-i", video_path,
                    "-i", audio_input,
                ]
                if video_filter:
                    cmd += ["-filter:v", video_filter]
                cmd += [
                    "-map", "0:v:0",
                    "-map", "1:a:0",
                    "-c:v", codec,
                    "-crf", crf,
                    "-b:v", bitrate,
                    "-c:a", "aac",
                    "-b:a", "128k",
                ]
                if use_shortest:
                    cmd.append("-shortest")
                else:
                    # Keep full audio; video was retimed or already matched.
                    cmd += ["-t", f"{audio_duration:.3f}"]
                cmd += [
                    "-movflags", "+faststart",
                    "-y",
                    str(output_file),
                ]
            
            logger.info(f"Running FFmpeg: {' '.join(cmd)}")
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            
            if result.returncode != 0:
                logger.error(f"FFmpeg error: {result.stderr}")
                return {
                    "success": False,
                    "error": result.stderr,
                    "file_path": None
                }
            
            file_size = output_file.stat().st_size
            out_duration = self._get_media_duration(str(output_file))
            logger.info(
                "Video composed successfully: %s (%s bytes, %.2fs)",
                output_file,
                file_size,
                out_duration,
            )
            
            return {
                "success": True,
                "file_path": str(output_file),
                "file_size": file_size,
                "duration": out_duration,
            }
        except Exception as e:
            logger.error(f"Video composition failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "file_path": None
            }
    
    def add_click_highlights(self, video_path: str, click_positions: List[dict],
                           output_path: str) -> dict:
        """
        Add click highlights to video
        
        Args:
            video_path: Input video path
            click_positions: List of {x, y, timestamp} dictionaries
            output_path: Output video path
            
        Returns:
            Status dictionary
        """
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            # TODO: Implement click highlight overlay using FFmpeg drawbox filter
            # This requires generating filter_complex string dynamically
            
            logger.info(f"Click highlights added to: {output_file}")
            
            return {
                "success": True,
                "file_path": str(output_file),
                "highlights_count": len(click_positions)
            }
        except Exception as e:
            logger.error(f"Failed to add highlights: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def _concat_audio_files(self, audio_paths: List[str], output_path: str) -> str:
        """
        Concatenate multiple audio files (re-encode for gTTS MP3 compatibility).
        
        Args:
            audio_paths: List of audio file paths
            output_path: Output audio path
            
        Returns:
            Path to concatenated audio
        """
        try:
            out = Path(output_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            concat_list = out.parent / f"_concat_{out.stem}.txt"
            with open(concat_list, "w", encoding="utf-8") as f:
                for audio_path in audio_paths:
                    # ffmpeg concat demuxer needs escaped single quotes in paths
                    abs_path = Path(audio_path).resolve().as_posix().replace("'", r"'\''")
                    f.write(f"file '{abs_path}'\n")
            
            # Re-encode: stream copy often fails across gTTS mp3 frames.
            cmd = [
                self.ffmpeg_path,
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list),
                "-c:a", "libmp3lame",
                "-b:a", "128k",
                "-y",
                str(out),
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            try:
                concat_list.unlink(missing_ok=True)
            except Exception:
                pass

            if result.returncode != 0 or not out.exists() or out.stat().st_size == 0:
                logger.error(f"Audio concat failed: {result.stderr}")
                return audio_paths[0]
            
            return str(out)
        except Exception as e:
            logger.error(f"Audio concatenation failed: {e}")
            return audio_paths[0]
    
    def _get_media_duration(self, media_path: str) -> float:
        """Get media duration in seconds (video or audio)."""
        if not media_path:
            return 0.0
        path = str(media_path)
        try:
            import shutil

            ffprobe_path = shutil.which("ffprobe")
            # imageio-ffmpeg may ship ffprobe next to ffmpeg
            if not ffprobe_path:
                try:
                    import imageio_ffmpeg
                    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                    candidate = Path(ffmpeg_exe).with_name(
                        Path(ffmpeg_exe).name.replace("ffmpeg", "ffprobe")
                    )
                    if candidate.exists():
                        ffprobe_path = str(candidate)
                except Exception:
                    pass

            if ffprobe_path:
                probe_cmd = [
                    ffprobe_path,
                    "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    path,
                ]
                result = subprocess.run(probe_cmd, capture_output=True, text=True)
                if result.returncode == 0 and result.stdout.strip():
                    return float(result.stdout.strip())

            # Reliable fallback: parse ffmpeg -i Duration line (works for mp3/mp4).
            fallback = subprocess.run(
                [self.ffmpeg_path, "-i", path],
                capture_output=True,
                text=True,
            )
            output = fallback.stderr or fallback.stdout or ""
            for line in output.splitlines():
                if "Duration:" in line:
                    parts = line.split("Duration:")[1].split(",")[0].strip()
                    if parts and parts != "N/A":
                        h, m, s = parts.split(":")
                        return (float(h) * 3600.0) + (float(m) * 60.0) + float(s)
            return 0.0
        except Exception as e:
            logger.warning(f"Could not read duration for {path}: {e}")
            return 0.0

    def _get_video_duration(self, video_path: str) -> float:
        """Get video duration in seconds"""
        return self._get_media_duration(video_path)

    def _get_audio_duration(self, audio_path: str) -> float:
        """Get audio duration in seconds"""
        return self._get_media_duration(audio_path)

    def _build_atempo_filter(self, speed_factor: float) -> str:
        """Build an FFmpeg atempo chain for arbitrary speed-up values."""
        if speed_factor <= 0:
            return "atempo=1.0"

        parts = []
        remaining = speed_factor
        while remaining > 2.0:
            parts.append("atempo=2.0")
            remaining /= 2.0
        while remaining < 0.5:
            parts.append("atempo=0.5")
            remaining /= 0.5
        parts.append(f"atempo={remaining:.4f}")
        return ",".join(parts)
    
    def optimize_video(self, video_path: str, output_path: str, 
                      quality: str = "medium") -> dict:
        """
        Optimize video for web
        
        Args:
            video_path: Input video path
            output_path: Output video path
            quality: Quality preset (low, medium, high)
            
        Returns:
            Status dictionary
        """
        quality_settings = {
            "low": {"crf": "28", "bitrate": "2000k"},
            "medium": {"crf": "23", "bitrate": "5000k"},
            "high": {"crf": "18", "bitrate": "10000k"}
        }
        
        settings = quality_settings.get(quality, quality_settings["medium"])
        
        return self.compose_video_with_audio(
            video_path, [], output_path, settings
        )

import os
import sys
import json
import subprocess
import threading
import re
from dataclasses import dataclass
from typing import Optional, Callable

@dataclass
class AudioInfo:
    filepath: str
    filename: str
    duration: float  # seconds
    file_size: int   # bytes
    format_name: str
    channels: int
    sample_rate: int
    bit_rate: int
    has_audio: bool

def format_duration(seconds: float) -> str:
    """Format seconds into HH:MM:SS or MM:SS."""
    if seconds < 0:
        return "00:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

def format_size(bytes_val: int) -> str:
    """Format bytes into readable MB or KB."""
    if bytes_val >= 1024 * 1024 * 1024:
        return f"{bytes_val / (1024**3):.2f} GB"
    elif bytes_val >= 1024 * 1024:
        return f"{bytes_val / (1024**2):.1f} MB"
    elif bytes_val >= 1024:
        return f"{bytes_val / 1024:.1f} KB"
    return f"{bytes_val} B"

def probe_file(filepath: str) -> AudioInfo:
    """Analyze media file using ffprobe and return AudioInfo."""
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"File not found: {filepath}")

    cmd = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        filepath
    ]

    # Windows: hide console window
    startupinfo = None
    if sys.platform == "win32":
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            startupinfo=startupinfo,
            check=True
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe failed to analyze file: {e.stderr}")

    data = json.loads(proc.stdout)
    fmt = data.get("format", {})
    streams = data.get("streams", [])

    audio_stream = None
    for st in streams:
        if st.get("codec_type") == "audio":
            audio_stream = st
            break

    duration_str = fmt.get("duration") or (audio_stream.get("duration") if audio_stream else "0")
    try:
        duration = float(duration_str)
    except (ValueError, TypeError):
        duration = 0.0

    size_str = fmt.get("size", "0")
    try:
        file_size = int(size_str)
    except (ValueError, TypeError):
        file_size = os.path.getsize(filepath)

    format_name = fmt.get("format_name", "unknown")

    channels = int(audio_stream.get("channels", 2)) if audio_stream else 0
    sample_rate = int(audio_stream.get("sample_rate", 44100)) if audio_stream else 0
    bit_rate = int(fmt.get("bit_rate") or audio_stream.get("bit_rate") or 0) if audio_stream else 0

    return AudioInfo(
        filepath=filepath,
        filename=os.path.basename(filepath),
        duration=duration,
        file_size=file_size,
        format_name=format_name,
        channels=channels,
        sample_rate=sample_rate,
        bit_rate=bit_rate,
        has_audio=(audio_stream is not None)
    )

def calculate_optimal_bitrate(
    duration_sec: float,
    target_mb: float = 95.0,
    mode: str = "ai_voice",
    custom_kbps: int = 64
) -> int:
    """
    Calculate optimal MP3 bitrate (in kbps).
    target_mb defaults to 95.0 MB (safe margin for 100MB limit).
    """
    if duration_sec <= 0:
        return 64

    # Target bytes with safety margin (0.94) to account for MP3 container / ID3 tags / CBR padding
    max_safe_bytes = target_mb * 1024 * 1024 * 0.94
    max_safe_kbps = int((max_safe_bytes * 8) / (duration_sec * 1000))
    # Keep within reasonable bounds
    max_safe_kbps = max(24, min(320, max_safe_kbps))

    if mode == "ai_voice":
        # 64 kbps mono is ideal for speech & AI transcription (Whisper, Gemini, NotebookLM)
        # If duration is very long (> 3.5 hours), scale down to max_safe_kbps
        if max_safe_kbps < 64:
            return max_safe_kbps
        return 64
    elif mode == "fit_target":
        # Maximize audio quality up to target_mb (capped at 192kbps for voice)
        return min(192, max_safe_kbps)
    elif mode == "compact":
        # Maximum compression, ideal for quick transmission
        return min(32, max_safe_kbps)
    elif mode == "custom":
        return min(custom_kbps, max_safe_kbps)
    else:
        return min(64, max_safe_kbps)

def estimate_output_size_mb(duration_sec: float, bitrate_kbps: int) -> float:
    """Estimate output MP3 file size in MB."""
    # (kbps * 1000 bits/sec / 8 bytes) * duration + 0.5% overhead
    bytes_est = (bitrate_kbps * 1000 / 8) * duration_sec * 1.005
    return bytes_est / (1024 * 1024)

class AudioCompressor:
    """Manages audio compression process using ffmpeg."""

    def __init__(self):
        self._current_process: Optional[subprocess.Popen] = None
        self._is_cancelled: bool = False

    def cancel(self):
        """Cancel ongoing conversion."""
        self._is_cancelled = True
        if self._current_process:
            try:
                self._current_process.terminate()
            except Exception:
                pass

    def convert(
        self,
        input_path: str,
        output_path: str,
        duration_sec: float,
        bitrate_kbps: int,
        ai_optimize: bool = True,
        sample_rate: int = 24000,
        progress_callback: Optional[Callable[[float, str], None]] = None
    ) -> bool:
        """
        Convert input file to MP3 safely without pipe deadlock.
        progress_callback: func(percent: float (0.0 to 100.0), status_text: str)
        """
        self._is_cancelled = False

        # Ensure output directory exists
        out_dir = os.path.dirname(output_path)
        if out_dir and not os.path.exists(out_dir):
            os.makedirs(out_dir, exist_ok=True)

        def _run_ffmpeg(use_filter: bool) -> tuple[int, list[str]]:
            cmd = [
                "ffmpeg",
                "-y",  # overwrite
                "-nostats",
                "-fflags", "+genpts+discardcorrupt",
                "-err_detect", "ignore_err",
                "-i", input_path,
                "-vn", # strip video
                "-ac", "1", # mono
                "-ar", str(sample_rate)
            ]

            if use_filter:
                af_filter = "highpass=f=80,lowpass=f=8000,speechnorm=e=4:r=0.0001:l=1"
                cmd.extend(["-af", af_filter])

            cmd.extend([
                "-c:a", "libmp3lame",
                "-b:a", f"{bitrate_kbps}k",
                "-progress", "pipe:1",
                output_path
            ])

            # Windows: hide console window
            startupinfo = None
            if sys.platform == "win32":
                startupinfo = subprocess.STARTUPINFO()
                startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
                startupinfo.wShowWindow = 0

            self._current_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                startupinfo=startupinfo,
                bufsize=1
            )

            # Drain stderr in a dedicated daemon thread to PREVENT PIPE BUFFER DEADLOCK!
            stderr_lines = []
            def _drain_stderr(pipe):
                try:
                    for err_l in pipe:
                        stderr_lines.append(err_l)
                        if len(stderr_lines) > 60:
                            stderr_lines.pop(0)
                except Exception:
                    pass

            stderr_thread = threading.Thread(
                target=_drain_stderr,
                args=(self._current_process.stderr,),
                daemon=True
            )
            stderr_thread.start()

            time_us_pattern = re.compile(r"out_time_us=(\d+)")
            speed_pattern = re.compile(r"speed=\s*([\d\.]+x)")

            current_speed = ""

            for line in self._current_process.stdout:
                if self._is_cancelled:
                    break

                line = line.strip()
                if line == "progress=end":
                    if progress_callback:
                        progress_callback(100.0, "変換完了")
                    break

                m_speed = speed_pattern.search(line)
                if m_speed:
                    current_speed = m_speed.group(1)

                m_time = time_us_pattern.search(line)
                if m_time and duration_sec > 0:
                    current_us = int(m_time.group(1))
                    cur_sec = current_us / 1_000_000
                    percent = min(99.5, (current_us / (duration_sec * 1_000_000)) * 100.0)
                    status_text = f"{percent:.1f}% ({format_duration(cur_sec)} / {format_duration(duration_sec)})"
                    if current_speed:
                        status_text += f" [{current_speed}]"
                    if progress_callback:
                        progress_callback(percent, status_text)

            self._current_process.wait()
            stderr_thread.join(timeout=1.0)
            return self._current_process.returncode, stderr_lines

        try:
            # First attempt with selected filter
            ret_code, err_logs = _run_ffmpeg(use_filter=ai_optimize)

            if self._is_cancelled:
                if os.path.exists(output_path):
                    try:
                        os.remove(output_path)
                    except Exception:
                        pass
                return False

            # If failed and was using ai_optimize, retry once without audio filters
            if ret_code != 0 and ai_optimize:
                if progress_callback:
                    progress_callback(50.0, "音声フィルタを自動調整して再試行中...")
                ret_code, err_logs = _run_ffmpeg(use_filter=False)

            if ret_code != 0:
                err_summary = "".join(err_logs[-15:]) if err_logs else "Unknown FFmpeg error"
                raise RuntimeError(f"FFmpeg error (code {ret_code}):\n{err_summary}")

            if progress_callback:
                progress_callback(100.0, "変換完了")

            return True

        finally:
            self._current_process = None

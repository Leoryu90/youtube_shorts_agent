"""
video.py — 이미지 + 오디오 + 자막 → 쇼츠 MP4 합성 (ffmpeg)

Phase 1: 단색 배경 + 나레이션 + 자막
Phase 2: 문장별 이미지 + 정확한 타이밍 자막
"""

import os
import subprocess
import tempfile
from pathlib import Path


def create_video(
    audio_path: str,
    script: list,
    output_path: str,
    config: dict = None,
) -> str:
    """
    단색 배경 버전 (하위 호환용)
    """
    config = config or {}
    segments = _script_to_segments_uniform(script, get_audio_duration(audio_path))
    return _render_video(
        background=config.get("background_color", "black"),
        audio_path=audio_path,
        segments=segments,
        output_path=output_path,
        config=config,
    )


def create_video_with_images(
    image_paths: list,
    audio_path: str,
    tts_segments: list,
    output_path: str,
    config: dict = None,
) -> str:
    """
    문장별 이미지 + TTS 실제 타이밍으로 쇼츠 MP4 생성

    Args:
        image_paths: 문장별 이미지 경로 리스트 (tts_segments와 길이 동일)
        audio_path: 합쳐진 나레이션 오디오
        tts_segments: synthesize_sentences() 결과
                      [{"text", "audio_path", "duration", "start", "end"}, ...]
        output_path: 출력 MP4 경로
        config: video 설정
    """
    config = config or {}
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    width, height = config.get("resolution", [1080, 1920])
    fps = config.get("fps", 30)

    import shutil, tempfile

    # 한글/공백 경로 문제 회피: ASCII 이름 임시 폴더 사용
    tmp_dir = tempfile.mkdtemp(prefix="vid_clips_")
    clip_paths = []

    # 1단계: 문장별 이미지 클립 생성
    for i, (img_path, seg) in enumerate(zip(image_paths, tts_segments)):
        clip_path = os.path.join(tmp_dir, f"c{i:04d}.mp4")
        duration = seg["duration"]
        abs_img = str(Path(img_path).resolve())

        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-t", str(duration),
            "-i", abs_img,
            "-vf", f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
                   f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:black",
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
            clip_path,
        ]
        subprocess.run(cmd, check=True, capture_output=True)
        clip_paths.append(clip_path)

    # 2단계: 클립 연결 (ASCII 경로만 사용)
    concat_path = os.path.join(tmp_dir, "concat.mp4")
    list_file = os.path.join(tmp_dir, "list.txt")
    with open(list_file, "w") as f:
        for cp in clip_paths:
            f.write(f"file '{cp.replace(chr(92), '/')}'\n")

    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
         "-c", "copy", concat_path],
        check=True, capture_output=True,
    )

    # 3단계: 오디오 + 자막 합성
    subtitle_filter = _build_subtitle_filters_timed(tts_segments, config)
    vf = ",".join(subtitle_filter) if subtitle_filter else "null"

    cmd = [
        "ffmpeg", "-y",
        "-i", concat_path,
        "-i", audio_path,
        "-vf", vf,
        "-map", "0:v",
        "-map", "1:a",
        "-shortest",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path,
    ]
    subprocess.run(cmd, check=True)

    # 임시 파일 정리
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return output_path


def get_audio_duration(audio_path: str) -> float:
    """ffprobe로 오디오 길이(초) 반환"""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


# ── 내부 함수 ─────────────────────────────────────────────────────────────────

def _render_video(
    background: str,
    audio_path: str,
    segments: list,
    output_path: str,
    config: dict,
) -> str:
    """단색 배경 + 자막 + 오디오로 MP4 생성"""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    width, height = config.get("resolution", [1080, 1920])
    fps = config.get("fps", 30)

    subtitle_filters = _build_subtitle_filters_timed(segments, config)
    vf = ",".join(subtitle_filters) if subtitle_filters else "null"

    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"color=c={background}:size={width}x{height}:rate={fps}",
        "-i", audio_path,
        "-vf", vf,
        "-shortest",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "23",
        "-c:a", "aac",
        "-b:a", "192k",
        output_path,
    ]
    subprocess.run(cmd, check=True)
    return output_path


def _script_to_segments_uniform(script: list, total_duration: float) -> list:
    """자막 타이밍을 균등 분할 (단색 배경 폴백용)"""
    if not script:
        return []
    chunk = total_duration / len(script)
    segments = []
    for i, text in enumerate(script):
        segments.append({
            "text": text,
            "start": round(i * chunk, 3),
            "end": round((i + 1) * chunk, 3),
            "duration": chunk,
        })
    return segments


def _build_subtitle_filters_timed(segments: list, config: dict) -> list:
    """
    실제 타이밍 기반 drawtext 필터 생성
    한국어 긴 문장은 자동 줄바꿈 처리
    """
    font_path = config.get("font_path", "C:/Windows/Fonts/malgun.ttf")
    font_size = config.get("font_size", 48)
    font_color = config.get("font_color", "white")
    border_color = config.get("font_border_color", "black")
    border_width = config.get("font_border_width", 2)
    width = config.get("resolution", [1080, 1920])[0]
    height = config.get("resolution", [1080, 1920])[1]

    font_path_escaped = font_path.replace("\\", "/").replace(":", "\\:")
    filters = []

    for seg in segments:
        lines = _wrap_korean(seg["text"], max_chars=18)
        start = seg["start"]
        end = seg["end"]

        # 줄 수에 따라 y 위치 조정 (여러 줄이면 위로 올림)
        line_height = font_size + 8
        total_text_height = len(lines) * line_height
        base_y = int(height * 0.78) - total_text_height // 2

        for j, line in enumerate(lines):
            text = _escape_ffmpeg(line)
            y = base_y + j * line_height

            filters.append(
                f"drawtext=fontfile='{font_path_escaped}'"
                f":text='{text}'"
                f":fontsize={font_size}"
                f":fontcolor={font_color}"
                f":bordercolor={border_color}"
                f":borderw={border_width}"
                f":x=(w-text_w)/2"
                f":y={y}"
                f":enable='between(t,{start:.3f},{end:.3f})'"
            )

    return filters


def _wrap_korean(text: str, max_chars: int = 18) -> list:
    """
    한국어 문장을 최대 글자 수 기준으로 줄바꿈
    공백 기준으로 먼저 분리, 없으면 글자 수로 자름
    """
    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    lines = []
    # 공백이 있으면 단어 단위로
    if " " in text:
        words = text.split(" ")
        current = ""
        for word in words:
            if len(current) + len(word) + 1 <= max_chars:
                current = current + " " + word if current else word
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
    else:
        # 공백 없는 한국어: 글자 수로 자름
        for i in range(0, len(text), max_chars):
            lines.append(text[i:i + max_chars])

    return lines if lines else [text]


def _escape_ffmpeg(text: str) -> str:
    """ffmpeg drawtext 특수문자 이스케이프"""
    return (
        text
        .replace("\\", "\\\\")
        .replace("'", "\\'")
        .replace(":", "\\:")
        .replace("%", "\\%")
    )

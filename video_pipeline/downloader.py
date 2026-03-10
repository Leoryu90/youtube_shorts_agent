"""
downloader.py — YouTube 영상/오디오/자막 다운로드 (yt-dlp)
"""

import os
from pathlib import Path
import yt_dlp


def download_video(url: str, output_dir: str = "data/raw") -> dict:
    """
    YouTube URL에서 오디오와 자막을 다운로드합니다.

    Returns:
        {
            "title": str,
            "audio_path": str,
            "subtitle_path": str | None,  # 자막 있으면 경로, 없으면 None
        }
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    result = {"title": None, "audio_path": None, "subtitle_path": None}

    # 1단계: 메타데이터 + 자막 가져오기 (실패해도 계속 진행)
    info_opts = {
        "quiet": True,
        "no_warnings": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["ko", "en"],
        "subtitlesformat": "vtt",
        "skip_download": True,
        "ignoreerrors": True,
        "outtmpl": str(Path(output_dir) / "%(title)s.%(ext)s"),
    }

    try:
        with yt_dlp.YoutubeDL(info_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            title = info.get("title", "untitled") if info else "untitled"
            result["title"] = _sanitize_filename(title)
    except Exception:
        # 자막 다운로드 실패 시 제목만 별도로 가져오기
        meta_opts = {"quiet": True, "skip_download": True}
        with yt_dlp.YoutubeDL(meta_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            result["title"] = _sanitize_filename(info.get("title", "untitled"))
        print("  자막 다운로드 실패 (429) → STT로 전환")

    # 자막 파일 탐색 (ko 우선, 없으면 en)
    for lang in ["ko", "en"]:
        subtitle_path = Path(output_dir) / f"{result['title']}.{lang}.vtt"
        if subtitle_path.exists():
            result["subtitle_path"] = str(subtitle_path)
            break

    # 2단계: 오디오 다운로드
    audio_path = str(Path(output_dir) / f"{result['title']}.wav")
    audio_opts = {
        "quiet": True,
        "format": "bestaudio/best",
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "wav",
            }
        ],
        "outtmpl": str(Path(output_dir) / f"{result['title']}.%(ext)s"),
    }

    with yt_dlp.YoutubeDL(audio_opts) as ydl:
        ydl.download([url])

    result["audio_path"] = audio_path
    return result


def _sanitize_filename(name: str) -> str:
    """파일명 및 ffmpeg 경로에서 문제 되는 문자 제거"""
    invalid = r'\/:*?"<>|\'[](),'
    for ch in invalid:
        name = name.replace(ch, "_")
    # 연속 언더스코어 정리
    import re
    name = re.sub(r"_+", "_", name)
    return name.strip("_").strip()

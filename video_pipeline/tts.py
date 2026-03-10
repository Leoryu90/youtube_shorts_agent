"""
tts.py — 텍스트 → 음성 파일 생성

engine="edge-tts"   : Microsoft TTS (사실상 무료, 클라우드)
engine="elevenlabs" : ElevenLabs API (Phase 2, 유료)
"""

import asyncio
import subprocess
from pathlib import Path


def synthesize(text: str, output_path: str, engine: str = "edge-tts", config: dict = None) -> str:
    """
    텍스트 전체를 하나의 오디오 파일로 생성 (단순 호출용)

    Returns:
        output_path
    """
    config = config or {}
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    if engine == "edge-tts":
        return _synthesize_edge_tts(text, output_path, config)
    elif engine == "elevenlabs":
        return _synthesize_elevenlabs(text, output_path, config)
    else:
        raise ValueError(f"지원하지 않는 engine: {engine}")


def synthesize_sentences(
    sentences: list, output_dir: str, engine: str = "edge-tts", config: dict = None
) -> list:
    """
    문장별로 개별 오디오 파일을 생성하고 실제 재생 시간을 반환합니다.
    이미지 타이밍 동기화에 사용됩니다.

    Returns:
        [
            {"text": str, "audio_path": str, "duration": float, "start": float, "end": float},
            ...
        ]
    """
    config = config or {}
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    segments = []
    cumulative = 0.0

    for i, sentence in enumerate(sentences):
        audio_path = str(Path(output_dir) / f"seg_{i:03d}.mp3")
        synthesize(sentence, audio_path, engine=engine, config=config)
        duration = _get_audio_duration(audio_path)

        segments.append(
            {
                "text": sentence,
                "audio_path": audio_path,
                "duration": duration,
                "start": round(cumulative, 3),
                "end": round(cumulative + duration, 3),
            }
        )
        cumulative += duration

    return segments


def concat_segments(segments: list, output_path: str) -> str:
    """
    synthesize_sentences() 결과를 하나의 오디오 파일로 합칩니다.

    Returns:
        output_path
    """
    import os, shutil, tempfile

    abs_output = str(Path(output_path).resolve())

    # 한글/공백 경로 문제 회피: 세그먼트를 ASCII 이름 임시 폴더로 복사
    tmp_dir = tempfile.mkdtemp(prefix="tts_concat_")
    try:
        list_file = os.path.join(tmp_dir, "list.txt")
        with open(list_file, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments):
                clean = os.path.join(tmp_dir, f"s{i:04d}.mp3")
                shutil.copy2(seg["audio_path"], clean)
                f.write(f"file '{clean.replace(chr(92), '/')}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file,
            "-c", "copy",
            abs_output,
        ]
        subprocess.run(cmd, check=True)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return output_path


# ── Phase 1: edge-tts ────────────────────────────────────────────────────────

def _synthesize_edge_tts(text: str, output_path: str, config: dict) -> str:
    import edge_tts

    voice = config.get("voice", "ko-KR-SunHiNeural")
    rate = config.get("rate", "+0%")
    volume = config.get("volume", "+0%")

    async def _run():
        communicate = edge_tts.Communicate(text, voice, rate=rate, volume=volume)
        await communicate.save(output_path)

    asyncio.run(_run())
    return output_path


# ── Phase 2: ElevenLabs ──────────────────────────────────────────────────────

def _synthesize_elevenlabs(text: str, output_path: str, config: dict) -> str:
    import os
    from elevenlabs.client import ElevenLabs
    from elevenlabs import save

    api_key = os.getenv("ELEVENLABS_API_KEY")
    if not api_key:
        raise EnvironmentError("ELEVENLABS_API_KEY 환경변수가 설정되지 않았습니다.")

    client = ElevenLabs(api_key=api_key)
    audio = client.generate(
        text=text,
        voice=config.get("voice_id", "Rachel"),
        model=config.get("model_id", "eleven_multilingual_v2"),
    )
    save(audio, output_path)
    return output_path


# ── 유틸 ─────────────────────────────────────────────────────────────────────

def _get_audio_duration(audio_path: str) -> float:
    """ffprobe로 오디오 길이(초) 반환"""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-show_entries", "format=duration",
        "-of", "csv=p=0",
        audio_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return float(result.stdout.strip())

"""
stt.py — 오디오 → 텍스트 변환 (faster-whisper, 로컬 CUDA)
"""

import os
import sys
from pathlib import Path


def _register_cuda_dlls():
    """pip으로 설치된 nvidia-cublas-cu12 등의 DLL 경로를 Windows PATH에 추가

    ctranslate2 C 확장은 Python add_dll_directory가 아닌 PATH를 직접 읽으므로
    os.environ["PATH"]에도 추가해야 합니다.
    """
    if sys.platform != "win32":
        return
    venv_root = Path(sys.executable).parent.parent
    nvidia_base = venv_root / "Lib" / "site-packages" / "nvidia"
    if not nvidia_base.exists():
        return
    extra = []
    for pkg_bin in nvidia_base.glob("*/bin"):
        if pkg_bin.is_dir():
            extra.append(str(pkg_bin))
            try:
                os.add_dll_directory(str(pkg_bin))
            except Exception:
                pass
    if extra:
        os.environ["PATH"] = os.pathsep.join(extra) + os.pathsep + os.environ.get("PATH", "")


_register_cuda_dlls()

from faster_whisper import WhisperModel

_model_cache: dict = {}


def _load_model(model_size: str, device: str, compute_type: str) -> WhisperModel:
    """모델 로드 (프로세스 내 캐시, 최초 1회 다운로드 후 재사용)"""
    key = (model_size, device, compute_type)
    if key not in _model_cache:
        print(f"  Whisper 모델 로드 중: {model_size} ({device})")
        _model_cache[key] = WhisperModel(model_size, device=device, compute_type=compute_type)
    return _model_cache[key]


def transcribe(audio_path: str, language: str = "ko", config: dict = None) -> dict:
    """
    오디오 파일을 텍스트로 변환합니다.

    Args:
        audio_path: WAV/MP3 파일 경로
        language: 언어 코드 ("ko", "en" 등)
        config: stt 설정 (config.yaml의 stt 섹션)

    Returns:
        {
            "text": str,           # 전체 텍스트 (이어붙임)
            "segments": list,      # [{"start": float, "end": float, "text": str}, ...]
        }
    """
    config = config or {}
    model_size = config.get("model_size", "base")
    device = config.get("device", "cuda")
    compute_type = config.get("compute_type", "float16")

    model = _load_model(model_size, device, compute_type)
    segments_iter, info = model.transcribe(
        audio_path,
        language=language,
        beam_size=5,
        vad_filter=True,  # 묵음 구간 제거
    )

    segments = []
    texts = []
    for seg in segments_iter:
        segments.append(
            {"start": round(seg.start, 2), "end": round(seg.end, 2), "text": seg.text.strip()}
        )
        texts.append(seg.text.strip())

    return {
        "text": " ".join(texts),
        "segments": segments,
    }


def parse_vtt_subtitle(vtt_path: str) -> dict:
    """
    VTT 자막 파일을 텍스트 + 세그먼트로 파싱합니다.
    자막이 있을 경우 STT를 건너뛰기 위해 사용합니다.
    """
    import re

    segments = []
    texts = []

    with open(vtt_path, "r", encoding="utf-8") as f:
        content = f.read()

    # 타임스탬프 + 텍스트 블록 파싱
    pattern = re.compile(
        r"(\d{2}:\d{2}:\d{2}\.\d{3}) --> (\d{2}:\d{2}:\d{2}\.\d{3})\n([\s\S]*?)(?=\n\n|\Z)"
    )
    for match in pattern.finditer(content):
        start_str, end_str, text = match.groups()
        text = re.sub(r"<[^>]+>", "", text).strip()  # HTML 태그 제거
        if not text:
            continue
        segments.append(
            {"start": _vtt_time_to_sec(start_str), "end": _vtt_time_to_sec(end_str), "text": text}
        )
        texts.append(text)

    return {"text": " ".join(texts), "segments": segments}


def _vtt_time_to_sec(time_str: str) -> float:
    """'00:01:23.456' → 초(float)"""
    h, m, s = time_str.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)

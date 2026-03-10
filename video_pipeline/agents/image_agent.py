"""
image_agent.py — 문장별 배경 이미지 생성

우선순위:
  1. Stable Diffusion (diffusers 설치 + GPU 있을 때)
  2. PIL 그라디언트 (폴백, 항상 동작)
"""

import hashlib
import random
from pathlib import Path


def generate_image(scene_text: str, output_path: str, config: dict = None) -> str:
    """
    문장 설명 → 배경 이미지 생성

    Args:
        scene_text: 해당 문장의 나레이션 텍스트 (이미지 프롬프트 기반으로 사용)
        output_path: 저장 경로 (.png)
        config: image 설정 (config.yaml의 image 섹션)

    Returns:
        output_path
    """
    config = config or {}
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    engine = config.get("engine", "auto")

    if engine == "gradient":
        return _generate_gradient(scene_text, output_path, config)
    elif engine == "sd":
        return _generate_sd(scene_text, output_path, config)
    else:  # "auto": SD 시도 → 실패 시 그라디언트
        try:
            return _generate_sd(scene_text, output_path, config)
        except Exception as e:
            print(f"  SD 생성 실패 ({e.__class__.__name__}) → 그라디언트 폴백")
            return _generate_gradient(scene_text, output_path, config)


def generate_images_for_script(
    sentences: list, output_dir: str, config: dict = None
) -> list:
    """
    스크립트의 각 문장에 대한 이미지를 순서대로 생성합니다.

    Returns:
        이미지 파일 경로 리스트
    """
    config = config or {}
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    image_paths = []

    for i, sentence in enumerate(sentences):
        output_path = str(Path(output_dir) / f"bg_{i:03d}.png")
        print(f"  이미지 생성 중 [{i+1}/{len(sentences)}]: {sentence[:20]}...")
        generate_image(sentence, output_path, config)
        image_paths.append(output_path)

    return image_paths


# ── Stable Diffusion ──────────────────────────────────────────────────────────

def _generate_sd(scene_text: str, output_path: str, config: dict) -> str:
    """
    Stable Diffusion으로 9:16 배경 이미지 생성
    설치: pip install diffusers transformers accelerate
          pip install torch --index-url https://download.pytorch.org/whl/cu121
    """
    import torch
    from diffusers import StableDiffusionPipeline, DPMSolverMultistepScheduler

    model_id = config.get("model_id", "runwayml/stable-diffusion-v1-5")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = torch.float16 if device == "cuda" else torch.float32
    steps = config.get("steps", 20)
    width = config.get("img_width", 576)
    height = config.get("img_height", 1024)

    # 모델 캐시 (프로세스 내 재사용)
    if not hasattr(_generate_sd, "_pipe") or _generate_sd._model_id != model_id:
        print(f"  SD 모델 로드 중: {model_id} ({device})")
        pipe = StableDiffusionPipeline.from_pretrained(model_id, torch_dtype=dtype)
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
        pipe = pipe.to(device)
        pipe.safety_checker = None  # 뉴스 콘텐츠 필터 비활성화
        _generate_sd._pipe = pipe
        _generate_sd._model_id = model_id

    prompt = _build_sd_prompt(scene_text, config)
    negative = config.get(
        "negative_prompt",
        "text, watermark, logo, blurry, low quality, ugly, distorted"
    )

    image = _generate_sd._pipe(
        prompt,
        negative_prompt=negative,
        width=width,
        height=height,
        num_inference_steps=steps,
    ).images[0]

    image.save(output_path)
    return output_path


def _build_sd_prompt(scene_text: str, config: dict) -> str:
    """
    한국어 나레이션 텍스트 → SD 프롬프트 생성
    Ollama가 있으면 영어 번역 + 최적화, 없으면 스타일 suffix만 추가
    """
    style_suffix = config.get(
        "style_suffix",
        "cinematic, dramatic lighting, high quality, 8k, photorealistic, vertical composition"
    )

    # Ollama로 프롬프트 최적화 시도
    try:
        import ollama
        ollama_model = config.get("ollama_model", "llama3")
        response = ollama.chat(
            model=ollama_model,
            messages=[{
                "role": "user",
                "content": (
                    f"Translate this Korean news text to a concise English image generation prompt "
                    f"(max 20 words, describe the visual scene only, no text/subtitles):\n{scene_text}"
                )
            }]
        )
        english_prompt = response["message"]["content"].strip()
        return f"{english_prompt}, {style_suffix}"
    except Exception:
        # Ollama 없으면 영어 스타일 suffix만
        return f"news background scene, abstract, {style_suffix}"


# ── PIL 그라디언트 (폴백) ──────────────────────────────────────────────────────

# 뉴스 테마별 그라디언트 색상 팔레트
_PALETTES = [
    ((10, 20, 40), (20, 40, 80)),    # 딥 네이비 (정치/사회)
    ((30, 10, 10), (70, 20, 20)),    # 딥 레드 (사건/사고)
    ((10, 30, 20), (20, 60, 40)),    # 딥 그린 (환경/경제)
    ((20, 20, 50), (40, 40, 90)),    # 퍼플 (과학/기술)
    ((40, 30, 10), (80, 60, 20)),    # 골드 (문화/스포츠)
    ((10, 30, 40), (20, 60, 80)),    # 틸 (국제)
]


def _generate_gradient(scene_text: str, output_path: str, config: dict) -> str:
    """PIL로 그라디언트 배경 이미지 생성"""
    from PIL import Image, ImageDraw, ImageFilter

    width, height = 1080, 1920

    # 텍스트 해시로 일관된 색상 선택 (같은 문장 → 같은 색상)
    idx = int(hashlib.md5(scene_text.encode()).hexdigest(), 16) % len(_PALETTES)
    top_color, bottom_color = _PALETTES[idx]

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)

    # 상하 그라디언트
    for y in range(height):
        ratio = y / height
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # 미세한 노이즈 텍스처 (단조로움 방지)
    img = img.filter(ImageFilter.GaussianBlur(radius=2))

    img.save(output_path)
    return output_path

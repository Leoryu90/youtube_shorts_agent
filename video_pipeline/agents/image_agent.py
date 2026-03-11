"""
image_agent.py — 문장별 배경 이미지 생성

우선순위 (engine=auto):
  1. Pollinations.ai (무료, API 키 없음, FLUX 모델)
  2. Stable Diffusion (diffusers 설치 + GPU 있을 때)
  3. PIL 그라디언트 (폴백, 항상 동작)
"""

import hashlib
import time
import urllib.parse
from pathlib import Path


def generate_image(scene_text: str, output_path: str, config: dict = None) -> str:
    """
    문장 설명 → 배경 이미지 생성

    engine 옵션:
        auto         : pollinations → sd → gradient 순서로 시도
        pollinations : Pollinations.ai API (무료, 키 불필요)
        sd           : Stable Diffusion (로컬)
        gradient     : PIL 그라디언트 (항상 동작)
    """
    config = config or {}
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    engine = config.get("engine", "auto")

    # 엔진별 시도 순서 결정
    if engine == "gradient":
        return _generate_gradient(scene_text, output_path, config)
    elif engine == "sd":
        pipeline = [(_generate_sd, "Stable Diffusion")]
    elif engine == "pollinations":
        pipeline = [(_generate_pollinations, "Pollinations.ai")]
    elif engine == "picsum":
        pipeline = [(_generate_picsum, "Picsum")]
    else:  # auto
        pipeline = [
            (_generate_pollinations, "Pollinations.ai"),
            (_generate_picsum, "Picsum"),
            (_generate_sd, "Stable Diffusion"),
        ]

    # 순서대로 시도, 모두 실패 시 그라디언트로 폴백
    for fn, name in pipeline:
        try:
            return fn(scene_text, output_path, config)
        except Exception as e:
            print(f"  {name} 실패 ({e.__class__.__name__}) → 그라디언트 폴백")
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


# ── Picsum (무료 랜덤 사진, 테스트용) ────────────────────────────────────────

def _generate_picsum(scene_text: str, output_path: str, config: dict) -> str:
    """
    picsum.photos에서 랜덤 실사 사진 다운로드 (API 키 불필요, 테스트용)
    """
    import requests, hashlib

    width = config.get("img_width", 576)
    height = config.get("img_height", 1024)
    # 같은 문장은 같은 seed → 동일 이미지 재현 가능
    seed = int(hashlib.md5(scene_text.encode()).hexdigest(), 16) % 1000

    url = f"https://picsum.photos/seed/{seed}/{width}/{height}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(resp.content)
    return output_path


# ── Pollinations.ai (무료, 키 불필요) ────────────────────────────────────────

def _generate_pollinations(scene_text: str, output_path: str, config: dict) -> str:
    """
    Pollinations.ai FLUX 모델로 이미지 생성
    설치: pip install requests  (이미 설치되어 있을 가능성 높음)
    """
    import requests

    prompt = _build_prompt_for_pollinations(scene_text, config)
    width = config.get("img_width", 576)
    height = config.get("img_height", 1024)
    model = config.get("pollinations_model", "flux")

    encoded = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded}"
        f"?width={width}&height={height}&model={model}&nologo=true&enhance=false"
    )

    # 500 등 서버 에러 시 1회 재시도
    for attempt in range(2):
        resp = requests.get(url, timeout=120)
        if resp.status_code < 500:
            break
        if attempt == 0:
            time.sleep(3)
    resp.raise_for_status()

    # 응답이 실제 이미지인지 확인
    content_type = resp.headers.get("content-type", "")
    if "image" not in content_type:
        raise ValueError(f"이미지가 아닌 응답: {content_type}")

    with open(output_path, "wb") as f:
        f.write(resp.content)

    # API 부하 방지 (연속 요청 시)
    time.sleep(0.5)
    return output_path


def _build_prompt_for_pollinations(scene_text: str, config: dict) -> str:
    """
    한국어 나레이션 → Pollinations 영어 프롬프트
    Ollama 있으면 번역, 없으면 키워드 기반 기본 프롬프트
    """
    style_suffix = config.get(
        "style_suffix",
        "cinematic dramatic lighting, high quality, photorealistic, vertical 9:16"
    )

    try:
        import ollama
        ollama_model = config.get("ollama_model", "llama3")
        response = ollama.chat(
            model=ollama_model,
            messages=[{
                "role": "user",
                "content": (
                    "Translate this Korean news sentence to a short English image prompt "
                    "(max 15 words, visual scene only, no text or UI elements):\n"
                    f"{scene_text}"
                )
            }]
        )
        english = response["message"]["content"].strip().strip('"')
        return f"{english}, {style_suffix}"
    except Exception:
        return f"Korean news dramatic scene, {style_suffix}"


# ── Stable Diffusion (로컬) ───────────────────────────────────────────────────

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

    if not hasattr(_generate_sd, "_pipe") or _generate_sd._model_id != model_id:
        print(f"  SD 모델 로드 중: {model_id} ({device})")
        pipe = StableDiffusionPipeline.from_pretrained(model_id, torch_dtype=dtype)
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
        pipe = pipe.to(device)
        pipe.safety_checker = None
        _generate_sd._pipe = pipe
        _generate_sd._model_id = model_id

    prompt = _build_prompt_for_pollinations(scene_text, config)  # 프롬프트 빌더 공유
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


# ── PIL 그라디언트 (폴백) ──────────────────────────────────────────────────────

_PALETTES = [
    ((10, 20, 40), (20, 40, 80)),
    ((30, 10, 10), (70, 20, 20)),
    ((10, 30, 20), (20, 60, 40)),
    ((20, 20, 50), (40, 40, 90)),
    ((40, 30, 10), (80, 60, 20)),
    ((10, 30, 40), (20, 60, 80)),
]


def _generate_gradient(scene_text: str, output_path: str, config: dict) -> str:
    """PIL로 그라디언트 배경 이미지 생성"""
    from PIL import Image, ImageDraw, ImageFilter

    width, height = 1080, 1920
    idx = int(hashlib.md5(scene_text.encode()).hexdigest(), 16) % len(_PALETTES)
    top_color, bottom_color = _PALETTES[idx]

    img = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / height
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    img = img.filter(ImageFilter.GaussianBlur(radius=2))
    img.save(output_path)
    return output_path

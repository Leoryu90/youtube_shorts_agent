"""
summarize.py — 텍스트 요약 + 쇼츠용 나레이션 스크립트 생성

mode="local" : 규칙 기반 or Ollama 로컬 LLM (무료)
mode="gpt"   : OpenAI GPT API (Phase 2)
"""


def summarize(text: str, mode: str = "local", max_chars: int = 180, config: dict = None) -> tuple:
    """
    Args:
        text: 원문 텍스트 (STT 결과 또는 자막)
        mode: "local" | "gpt"
        max_chars: 목표 스크립트 길이 (한국어 기준, 55초 ≈ 180자)
        config: summarize 설정 (config.yaml의 summarize 섹션)

    Returns:
        (summary: str, script: list[str])
        - summary: 한 문단 요약
        - script: 나레이션용 문장 리스트 (tts.py에 전달)
    """
    config = config or {}

    if mode == "local":
        return _summarize_local(text, max_chars, config)
    elif mode == "gpt":
        return _summarize_gpt(text, max_chars, config)
    else:
        raise ValueError(f"지원하지 않는 mode: {mode}. 'local' 또는 'gpt'를 사용하세요.")


# ── Phase 1: 로컬 요약 ──────────────────────────────────────────────────────

def _summarize_local(text: str, max_chars: int, config: dict) -> tuple:
    """
    1차: 단순 문장 분리 + 앞부분 추출
    Ollama가 설치되어 있으면 LLM 요약으로 자동 전환
    """
    ollama_model = config.get("ollama_model", "llama3")

    try:
        return _summarize_ollama(text, max_chars, ollama_model)
    except Exception:
        # Ollama 없거나 실패 시 규칙 기반으로 폴백
        return _summarize_rule_based(text, max_chars)


def _summarize_ollama(text: str, max_chars: int, model: str) -> tuple:
    """Ollama 로컬 LLM으로 요약"""
    import ollama

    prompt = f"""다음 텍스트를 유튜브 쇼츠용 나레이션으로 요약해주세요.
조건:
- 총 {max_chars}자 이내
- 핵심 내용만 간결하게
- 자연스러운 구어체
- 문장을 줄바꿈으로 구분

텍스트:
{text[:3000]}

요약:"""

    response = ollama.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response["message"]["content"].strip()
    sentences = [s.strip() for s in raw.split("\n") if s.strip()]
    summary = " ".join(sentences)
    return summary, sentences


def _summarize_rule_based(text: str, max_chars: int) -> tuple:
    """Ollama 없을 때 폴백: 앞부분 문장 추출"""
    sentences = []
    for chunk in text.replace("。", ".").replace("！", "!").replace("？", "?").split("."):
        chunk = chunk.strip()
        if chunk:
            sentences.append(chunk + ".")

    script = []
    total = 0
    for s in sentences:
        if total + len(s) > max_chars:
            break
        script.append(s)
        total += len(s)

    summary = " ".join(script)
    return summary, script


# ── Phase 2: GPT 요약 ────────────────────────────────────────────────────────

def _summarize_gpt(text: str, max_chars: int, config: dict) -> tuple:
    """OpenAI GPT API로 요약 (Phase 2에서 활성화)"""
    import openai

    prompt = f"""다음 텍스트를 유튜브 쇼츠용 나레이션으로 요약해주세요.
조건:
- 총 {max_chars}자 이내
- 핵심 내용만 간결하게
- 자연스러운 구어체
- 각 문장을 줄바꿈으로 구분

텍스트:
{text[:4000]}"""

    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        max_tokens=500,
    )
    raw = response.choices[0].message.content.strip()
    sentences = [s.strip() for s in raw.split("\n") if s.strip()]
    summary = " ".join(sentences)
    return summary, sentences

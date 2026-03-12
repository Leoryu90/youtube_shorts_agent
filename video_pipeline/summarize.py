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
    """Ollama 로컬 LLM으로 요약 (긴 텍스트는 청크 map-reduce)"""
    import ollama

    CHUNK_SIZE = 3000

    SYSTEM_PROMPT = (
        "너는 유튜브 쇼츠 뉴스 나레이션 작가야. "
        "항상 3인칭 객관적 뉴스 문체로 써. '저는', '우리는', '제가' 같은 1인칭 표현 절대 금지. "
        "텍스트에 STT 오타, 잘못된 한자, 문맥에 맞지 않는 단어가 있으면 자연스러운 한국어로 교정해. "
        "나레이션 문장만 출력해. 설명, 머리말, 조건 언급 없이 오직 나레이션 본문만 출력해."
    )

    def call_ollama(system: str, user: str) -> str:
        response = ollama.chat(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        )
        return response["message"]["content"].strip()

    # 청크 분리
    chunks = [text[i:i+CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]

    if len(chunks) > 1:
        # Map: 청크별 중간 요약
        chunk_summaries = []
        for i, chunk in enumerate(chunks):
            user_msg = f"다음 텍스트({i+1}/{len(chunks)}번 구간)의 핵심 내용을 3~5문장으로 요약해. STT 오타나 한자는 자연스러운 한국어로 교정해. 요약 문장만 출력.\n\n{chunk}"
            chunk_summaries.append(call_ollama(SYSTEM_PROMPT, user_msg))

        # Reduce: 최종 나레이션
        combined = "\n".join(chunk_summaries)
        user_msg = f"아래 요약들을 합쳐서 쇼츠 나레이션을 만들어. {max_chars}자 내외로 자연스럽게 끊어. 구어체로, 각 문장은 줄바꿈으로 구분. 나레이션 문장만 출력.\n\n{combined}"
        raw = call_ollama(SYSTEM_PROMPT, user_msg)
    else:
        # 짧은 텍스트
        user_msg = f"다음 텍스트를 쇼츠 나레이션으로 요약해. {max_chars}자 내외로 자연스럽게 끊어. 구어체로, 각 문장은 줄바꿈으로 구분. 나레이션 문장만 출력.\n\n{text}"
        raw = call_ollama(SYSTEM_PROMPT, user_msg)

    sentences = _clean_llm_output(raw)
    summary = " ".join(sentences)
    return summary, sentences


def _clean_llm_output(raw: str) -> list:
    """LLM 출력에서 bullet, 번호, 따옴표, 머리말 등 제거 후 문장 리스트 반환"""
    import re
    lines = []
    for line in raw.split("\n"):
        line = line.strip()
        if not line:
            continue
        # bullet, 번호 제거: "1. ", "- ", "• " 등
        line = re.sub(r'^[\d]+[\.\)]\s*', '', line)
        line = re.sub(r'^[-•*]\s*', '', line)
        # 앞뒤 따옴표 제거
        line = line.strip('"\'"""')
        line = line.strip()
        if line:
            lines.append(line)
    return lines


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

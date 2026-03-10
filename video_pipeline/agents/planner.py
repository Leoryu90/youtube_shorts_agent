"""
planner.py — 콘텐츠 기획 에이전트 (Phase 3)

주제를 입력받아 쇼츠 시나리오를 씬 단위로 생성합니다.
각 씬은 이미지 프롬프트 + 나레이션 텍스트로 구성됩니다.
"""

# TODO: Phase 3 구현
# 예상 출력 형식:
# [
#   {
#     "scene_index": 0,
#     "duration_hint": 8,       # 예상 길이 (초)
#     "narration": "도입부 나레이션 텍스트",
#     "visual_description": "배경 이미지 설명 (한국어)",
#   },
#   ...
# ]


def plan(topic: str, total_duration: int = 55, config: dict = None) -> list:
    """
    주제 → 씬 기반 시나리오 생성

    Args:
        topic: 쇼츠 주제 (예: "AI가 바꾸는 미래 직업")
        total_duration: 목표 영상 길이 (초)
        config: 기획 관련 설정

    Returns:
        씬 리스트 (각 씬: narration, visual_description, duration_hint)
    """
    raise NotImplementedError("Phase 3에서 구현 예정")

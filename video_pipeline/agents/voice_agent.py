"""
voice_agent.py — 음성 생성 에이전트 (Phase 3)

씬별 나레이션 텍스트 → 개별 오디오 파일 생성
Phase 1의 tts.py를 씬 단위로 호출합니다.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from tts import synthesize

# TODO: Phase 3 구현


def generate_voice_for_scenes(scenes: list, output_dir: str, config: dict = None) -> list:
    """
    씬 리스트의 나레이션을 개별 오디오 파일로 생성 (병렬 처리 예정)

    Args:
        scenes: planner.py가 생성한 씬 리스트
        output_dir: 오디오 저장 디렉토리
        config: tts 설정

    Returns:
        씬별 오디오 파일 경로 리스트
    """
    raise NotImplementedError("Phase 3에서 구현 예정")
    # TODO: concurrent.futures로 병렬 생성
    # from concurrent.futures import ThreadPoolExecutor
    # with ThreadPoolExecutor() as executor:
    #     futures = [executor.submit(synthesize, scene["narration"], ...) for scene in scenes]

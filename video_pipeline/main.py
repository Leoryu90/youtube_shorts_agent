"""
main.py — YouTube 쇼츠 자동 생성 엔트리포인트

사용법:
  python main.py --url "https://youtube.com/watch?v=..."
  python main.py --url "..." --config config.yaml
"""

import argparse
import sys
import yaml
from pathlib import Path
from datetime import datetime

# 에이전트 폴더를 import 경로에 추가
sys.path.insert(0, str(Path(__file__).parent / "agents"))

from downloader import download_video
from stt import transcribe, parse_vtt_subtitle
from summarize import summarize
from tts import synthesize_sentences, concat_segments
from video import create_video_with_images
from image_agent import generate_images_for_script


def load_config(config_path: str = "config.yaml") -> dict:
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def run(url: str, config_path: str = "config.yaml") -> str:
    config = load_config(config_path)
    paths = config["paths"]

    # ── 1단계: 다운로드 ───────────────────────────────────────────────────────
    print("[1/6] 다운로드 중...")
    video_info = download_video(url, output_dir=paths["raw"])
    title = video_info["title"]
    print(f"  제목: {title}")

    # ── 2단계: 텍스트 추출 (자막 우선, 없으면 STT) ───────────────────────────
    print("[2/6] 텍스트 추출 중...")
    if video_info.get("subtitle_path"):
        print("  자막 파일 사용")
        transcript = parse_vtt_subtitle(video_info["subtitle_path"])
    else:
        print("  자막 없음 → Whisper STT 실행")
        transcript = transcribe(
            video_info["audio_path"],
            language=config["pipeline"]["language"],
            config=config["stt"],
        )
    print(f"  텍스트 {len(transcript['text'])}자 추출 완료")

    # 트랜스크립트 저장
    transcript_dir = Path(paths["transcripts"])
    transcript_dir.mkdir(parents=True, exist_ok=True)
    (transcript_dir / f"{title}.txt").write_text(transcript["text"], encoding="utf-8")

    # ── 3단계: 요약 + 스크립트 생성 ──────────────────────────────────────────
    print("[3/6] 요약 및 스크립트 생성 중...")
    summary, script = summarize(
        transcript["text"],
        mode=config["summarize"]["mode"],
        max_chars=config["summarize"]["max_chars"],
        config=config["summarize"],
    )
    print(f"  스크립트 {len(script)}문장 생성 완료")
    (transcript_dir / f"{title}_script.txt").write_text("\n".join(script), encoding="utf-8")

    # ── 4단계: 배경 이미지 생성 (문장별) ─────────────────────────────────────
    print("[4/6] 배경 이미지 생성 중...")
    image_dir = str(Path(paths["raw"]) / "images")
    image_paths = generate_images_for_script(
        script, output_dir=image_dir, config=config.get("image", {})
    )

    # ── 5단계: TTS 음성 생성 (문장별 + 타이밍) ───────────────────────────────
    print("[5/6] TTS 음성 생성 중...")
    audio_dir = Path(paths["audio"])
    audio_dir.mkdir(parents=True, exist_ok=True)
    seg_dir = str(audio_dir / "segments")

    tts_segments = synthesize_sentences(
        script,
        output_dir=seg_dir,
        engine=config["tts"]["engine"],
        config=config["tts"],
    )

    total_duration = sum(s["duration"] for s in tts_segments)
    print(f"  총 나레이션 길이: {total_duration:.1f}초")

    # 오디오 합치기
    narration_path = str(audio_dir / f"{title}_narration.mp3")
    concat_segments(tts_segments, narration_path)

    # ── 6단계: 영상 합성 ─────────────────────────────────────────────────────
    print("[6/6] 영상 합성 중...")
    date_str = datetime.now().strftime("%Y%m%d")
    output_dir = Path(paths["output"])
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = str(output_dir / f"{date_str}_{title}.mp4")

    create_video_with_images(
        image_paths=image_paths,
        audio_path=narration_path,
        tts_segments=tts_segments,
        output_path=output_path,
        config=config.get("video", {}),
    )

    print(f"\n완료: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="YouTube 쇼츠 자동 생성기")
    parser.add_argument("--url", required=True, help="YouTube URL")
    parser.add_argument("--config", default="config.yaml", help="설정 파일 경로")
    args = parser.parse_args()

    run(args.url, args.config)

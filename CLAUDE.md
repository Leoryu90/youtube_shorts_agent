# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

YouTube 영상을 입력받아 쇼츠 MP4를 자동 생성하는 파이프라인입니다.
최종 목표는 주제 텍스트 → AI 멀티에이전트 → 쇼츠 영상 자동 생성입니다.

**개발 단계:**
- Phase 1 (현재): YouTube URL → 요약 → 쇼츠 MP4 (로컬/무료)
- Phase 2: 유료 API(GPT, ElevenLabs) 교체
- Phase 3: 주제 입력 → 에이전트 시스템 → 쇼츠 생성

## 실행 방법

```bash
cd video_pipeline
python main.py --url "https://youtube.com/watch?v=..."
python main.py --url "..." --config config.yaml
```

## 의존성 설치

```bash
pip install -r requirements.txt
```

ffmpeg은 별도 설치 필요 (PATH에 추가):
- Windows: https://ffmpeg.org/download.html

Ollama(로컬 LLM, 선택사항):
- https://ollama.com 에서 설치 후 `ollama pull llama3`

## 환경 변수

`.env.example`을 `.env`로 복사 후 작성:

- `OPENAI_API_KEY` — Phase 2 GPT 요약 시 필요
- `ELEVENLABS_API_KEY` — Phase 2 TTS 교체 시 필요

## 아키텍처

```
video_pipeline/
├── main.py              # 엔트리포인트: URL → MP4
├── config.yaml          # 모드/엔진 스위치 (mode=, engine=)
├── downloader.py        # yt-dlp: 오디오/자막 다운로드
├── stt.py               # faster-whisper: 오디오 → 텍스트
├── summarize.py         # 요약 + 나레이션 스크립트 생성
├── tts.py               # 텍스트 → 음성 파일
├── video.py             # ffmpeg: 오디오 + 자막 → MP4
└── agents/              # Phase 3: 주제 → 에이전트 시스템
    ├── planner.py       # 씬 기반 시나리오 기획
    ├── image_agent.py   # DALL-E 이미지 생성
    └── voice_agent.py   # 씬별 음성 생성 (병렬)
```

### 무료↔유료 전환 방식

`config.yaml`의 값만 변경하면 코드 수정 없이 전환됩니다:

```yaml
summarize:
  mode: local   # → gpt (OpenAI)
tts:
  engine: edge-tts  # → elevenlabs
```

### 주요 설계 결정

- **자막 우선**: 자막 있으면 STT 건너뜀 (`stt.parse_vtt_subtitle`)
- **Ollama 자동 폴백**: Ollama 미설치 시 rule-based 요약으로 자동 전환
- **자막 타이밍**: Phase 1은 균등 분할, Phase 2에서 TTS 세그먼트 기반으로 정밀화 예정
- **한글 폰트**: ffmpeg drawtext에 `C:/Windows/Fonts/malgun.ttf` 명시 필요

### GPU 설정 (RTX 2070 Super)

```yaml
stt:
  device: cuda
  compute_type: float16
```

CPU 환경에서는 `device: cpu`, `compute_type: float32`로 변경.

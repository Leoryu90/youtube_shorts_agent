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
pip install requests Pillow  # 이미지 생성 필수
```

ffmpeg은 별도 설치 필요 (PATH에 추가):
- Windows: https://ffmpeg.org/download.html

CUDA GPU 사용 시 (RTX 2070 Super 기준):
```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```
→ `stt.py`가 시작 시 자동으로 DLL 경로를 PATH에 등록함

Ollama (로컬 LLM, 선택사항):
- https://ollama.com 에서 설치 후 `ollama pull llama3`

## 환경 변수

`.env.example`을 `.env`로 복사 후 작성:

- `OPENAI_API_KEY` — Phase 2 GPT 요약 시 필요
- `ELEVENLABS_API_KEY` — Phase 2 TTS 교체 시 필요

## 아키텍처

```
video_pipeline/
├── main.py              # 엔트리포인트: URL → MP4 (6단계 파이프라인)
├── config.yaml          # 모드/엔진 스위치
├── downloader.py        # yt-dlp: 오디오/자막 다운로드
├── stt.py               # faster-whisper: 오디오 → 텍스트 + CUDA DLL 자동 등록
├── summarize.py         # 요약 + 나레이션 스크립트 생성
├── tts.py               # 텍스트 → 문장별 음성 파일 + 타이밍 반환
├── video.py             # ffmpeg: 이미지 시퀀스 + 오디오 + 자막 → MP4
└── agents/
    └── image_agent.py   # 배경 이미지 생성 (엔진 선택 + 자동 폴백)
```

### 파이프라인 흐름 (main.py)

```
1. 다운로드      (downloader.py)   YouTube → 오디오/자막
2. 텍스트 추출   (stt.py)          자막 우선, 없으면 Whisper STT
3. 요약          (summarize.py)    전체 텍스트 → 나레이션 문장 리스트
4. 이미지 생성   (image_agent.py)  문장별 배경 이미지
5. TTS           (tts.py)          문장별 음성 + 실제 재생 시간 반환
6. 영상 합성     (video.py)        이미지+오디오+자막 → 쇼츠 MP4
```

### config.yaml 주요 스위치

```yaml
stt:
  device: cuda          # cpu | cuda
  compute_type: float16 # int8 (cpu) | float16 (cuda)
  model_size: large-v3  # tiny | base | small | medium | large-v3

summarize:
  mode: local           # local (Ollama/rule-based) | gpt

tts:
  engine: edge-tts      # edge-tts | elevenlabs

image:
  engine: picsum        # picsum | pollinations | auto | sd | gradient
```

`config.yaml` 값만 변경하면 코드 수정 없이 엔진 교체됩니다.

### 주요 설계 결정

- **자막 우선**: 자막 있으면 STT 건너뜀 (`stt.parse_vtt_subtitle`)
- **Ollama 자동 폴백**: Ollama 미설치 시 rule-based 요약으로 자동 전환
- **이미지 폴백 체인**: pollinations → picsum → sd → gradient 순서로 자동 전환
- **TTS 타이밍**: `synthesize_sentences()`가 문장별 실제 재생 시간을 반환, 이미지 전환 타이밍과 자막에 사용
- **한글 경로 문제**: ffmpeg concat demuxer가 한글/공백 경로를 처리 못함 → 임시 ASCII 디렉토리에 복사 후 처리 (`tts.concat_segments`, `video.create_video_with_images`)
- **한글 폰트**: ffmpeg drawtext에 `C:/Windows/Fonts/malgun.ttf` 명시 필요
- **CUDA DLL**: `nvidia-cublas-cu12` pip 패키지의 DLL이 자동으로 PATH에 등록되지 않으므로 `stt._register_cuda_dlls()`가 모듈 로드 시 PATH에 추가

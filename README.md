# AI Daily Briefing Generator

Google RSS 피드로 뉴스를 수집하고 Claude API로 분석해 HTML 뉴스레터 + 음성 파일을 생성하는 자동화 도구.
GitHub Actions로 매일 아침 6시(KST)에 자동 실행되어 GitHub Pages에 배포됩니다.

## 구조

```
ai_daily_briefing/
├── ai_daily_briefing.py        # 메인 스크립트 (Anthropic Claude)
├── ai_daily_briefing_openai.py # OpenAI 버전
├── briefing_core.py            # 공통 로직 (RSS, 프롬프트, 파싱, TTS, HTML)
├── send_email.py               # 구독자 이메일 발송
├── isu_context.md              # 회사 맞춤 인사이트 컨텍스트
├── .github/workflows/
│   └── daily-briefing.yml      # GitHub Actions 자동화
├── docs/                       # GitHub Pages 배포 디렉토리
└── output/                     # 로컬 생성 결과물 (gitignore)
    ├── ai_briefing_YYYY_MM_DD.html
    ├── ai_briefing_YYYY_MM_DD.json
    └── ai_briefing_YYYY_MM_DD.mp3
```

## 빠른 시작

```bash
# 1. 의존성 설치
pip install anthropic feedparser requests

# 2. API 키 설정
export ANTHROPIC_API_KEY="sk-ant-..."

# 3. 실행
python ai_daily_briefing.py

# 4. 결과 확인
open output/ai_briefing_$(date +%Y_%m_%d).html
```

### TTS 음성 파일 생성 (선택)

GCP Cloud Text-to-Speech API Key를 설정하면 MP3 파일이 함께 생성됩니다.

```bash
export GCP_TTS_KEY="AIzaSy..."
python ai_daily_briefing.py
# → output/ai_briefing_YYYY_MM_DD.mp3 생성
# → HTML 우하단에 오디오 플레이어 삽입
```

GCP 콘솔 → APIs & Services → Credentials → API Key 발급 후 Cloud Text-to-Speech API 제한 설정 권장.

## 작동 원리

```mermaid
flowchart TD
    CRON["⏰ cron-job.org → GitHub Actions<br/>매일 KST 06:00"] --> MAIN
    DEV["develop 브랜치 push"] -.-> PREVIEW_WF["Preview 워크플로"]

    subgraph MAIN["ai_daily_briefing.py"]
        direction TB

        subgraph S1["① AI 뉴스"]
            RSS1["RSS 6개 수집<br/>Google News x3, TechCrunch,<br/>VentureBeat, The Verge"]
            FILTER1{"기간 내 기사<br/>5개 이상?"}
            EXPAND1["기간 2배 확장<br/>24h → 48h → 72h"]
            PROMPT1["시스템 프롬프트 생성<br/>+ ISU_COMPANY.md"]
            CLAUDE1["Claude API<br/>5개 선별 + 분석"]
            RAW1[("raw.txt 저장")]
            RSS1 --> FILTER1
            FILTER1 -- 아니오 --> EXPAND1 --> RSS1
            FILTER1 -- 예 --> PROMPT1 --> CLAUDE1 --> RAW1
        end

        subgraph PARSE["JSON 파싱 parse_news_json"]
            EXTRACT["json 코드블록 추출<br/>또는 중괄호 매칭"]
            FIXSTR["fix_json_string<br/>제어문자, 끝 쉼표 정리"]
            LOAD{"json.loads<br/>성공?"}
            FIXLLM["Claude에 JSON 수리 요청"]
            INJECT["inject_article_urls<br/>article_ref → 원문 url"]
            EXTRACT --> FIXSTR --> LOAD
            LOAD -- 아니오 --> FIXLLM --> INJECT
            LOAD -- 예 --> INJECT
        end

        FAIL["❌ 파싱 실패<br/>exit 1 → 워크플로 중단"]

        subgraph S2["② TTS (선택)"]
            TTSCHK{"GCP_TTS_KEY<br/>있음?"}
            TTSTXT["낭독 원고 생성<br/>특수문자 제거, 발음 치환"]
            TTSAPI["4900B 청크로 나눠<br/>GCP Wavenet-D 합성"]
            MP3[("mp3 저장")]
            TTSCHK -- 예 --> TTSTXT --> TTSAPI --> MP3
        end

        subgraph S3["③ 국내 IT 기업 동향 (실패해도 계속 진행)"]
            RSS2["Google News KR 5개<br/>M&A, 투자, 인사, 전략, 실적"]
            CLAUDE2["Claude API<br/>5개 선별 + 분석"]
            PARSE2["JSON 파싱 + URL 주입"]
            ITJSON[("it_company json 저장")]
            RSS2 --> CLAUDE2 --> PARSE2 --> ITJSON
        end

        subgraph S4["④ 렌더링"]
            HTML["generate_html<br/>탭1: AI 브리핑<br/>탭2: IT 동향 또는 빈 화면"]
            OUT[("output/<br/>html, json, mp3")]
            HTML --> OUT
        end

        RAW1 --> EXTRACT
        PARSE -. 최종 실패 .-> FAIL
        INJECT --> TTSCHK
        TTSCHK -- 아니오 --> RSS2
        MP3 --> RSS2
        ITJSON --> HTML
        RSS2 -. 예외 .-> HTML
    end

    OUT --> COPY["output → docs/ 복사<br/>최신본 → docs/index.html"]
    COPY --> PUSH["git commit & push"]
    PUSH --> PAGES["🌐 GitHub Pages"]
    PUSH --> EMAIL["send_email.py<br/>메일용 HTML 변환 후<br/>subscribers.txt 전원 발송"]

    PREVIEW_WF -.-> PREV_OUT["main의 docs/preview/에 배포"]
```

- 별도의 뉴스 API 없이 Google RSS 피드로 수집
- 회사 맞춤 인사이트는 `isu_context.md`에 컨텍스트 정의

## GitHub Actions 자동화

매일 KST 06:00에 외부 스케줄러(cron-job.org)가 `workflow_dispatch` API를 호출해 실행합니다. 설정 방법은 [SCHEDULING.md](SCHEDULING.md) 참고.

저장소 Secrets에 등록 필요:

| Secret | 설명 |
|--------|------|
| `ANTHROPIC_API_KEY` | Claude API 키 (필수) |
| `GCP_TTS_KEY` | GCP TTS API 키 (선택, 없으면 TTS 생략) |
| `GMAIL_ADDRESS` | 발송 Gmail 주소 (이메일 발송 시) |
| `GMAIL_APP_PASSWORD` | Gmail 앱 비밀번호 (이메일 발송 시) |

실행 순서: 브리핑 생성 → docs/ 복사 → commit & push → 이메일 발송

## 비용

| 항목 | 단가 | 1회 비용 |
|------|------|----------|
| Claude Sonnet 4.6 | $3/$15 per 1M tokens | ~$0.03~$0.05 |
| GCP WaveNet TTS | $16 per 1M chars | ~$0.01 |
| **합계** | | **~$0.04~$0.06 (≈60~90원)** |

월 30회 실행 시 약 1,800~2,700원 수준.

## 커스터마이징

### 뉴스 주제 변경
`collect_and_analyze_news()`의 `system_prompt`를 수정.

### 회사 맞춤 인사이트
`isu_context.md`에 회사/조직 컨텍스트를 작성하면 각 뉴스에 맞춤 인사이트가 추가됩니다.

### TTS 목소리 변경
`generate_tts_audio()`의 `voice.name` 수정:
- `ko-KR-Wavenet-A` ~ `ko-KR-Wavenet-D` (남/여 4종)

### 모델 변경
- `claude-sonnet-5-5`: 기본 추천 (가성비)
- `claude-opus-5-5`: 더 깊은 분석 (비용 ~5x)
- `claude-haiku-4-5`: 비용 최소화

# AI Daily Briefing Generator

Claude API + Web Search를 활용한 AI 뉴스레터 반자동화 도구

## 구조

```
ai_daily_briefing/
├── ai_daily_briefing.py    # 메인 스크립트
├── README.md               # 이 파일
└── output/                 # 생성된 HTML/JSON (자동 생성)
    ├── ai_briefing_2026_03_20.html
    └── ai_briefing_2026_03_20.json
```

## 빠른 시작

```bash
# 1. 의존성 설치
pip install anthropic

# 2. API 키 설정
export ANTHROPIC_API_KEY="sk-ant-..."

# 3. 실행
python ai_daily_briefing.py

# 4. 결과 확인
open output/ai_briefing_2026_03_20.html
```

## 작동 원리

```
[실행] → [Claude API + web_search 도구]
         Claude가 직접 웹 검색 → 뉴스 5개 선별 → JSON 출력
       → [JSON 파싱]
       → [HTML 템플릿 렌더링]
       → output/ 디렉토리에 저장
```

핵심 포인트: 별도의 뉴스 API(NewsAPI 등)가 필요 없습니다.
Claude의 `web_search` 서버 도구가 검색 + 분석을 한번에 처리합니다.

## 비용

| 항목 | 단가 | 1회 비용 |
|------|------|----------|
| Web Search | $10/1,000 검색 | ~$0.05~$0.10 |
| Claude Sonnet 4.6 토큰 | $3/$15 per 1M | ~$0.03~$0.05 |
| **합계** | | **~$0.08~$0.15 (≈100~200원)** |

월 30회 실행 시 약 3,000~4,500원 수준입니다.

## 매일 자동 실행 (cron)

```bash
# crontab 편집
crontab -e

# 매일 아침 7시에 실행
0 7 * * * cd /path/to/ai_daily_briefing && /usr/bin/python3 ai_daily_briefing.py >> /var/log/ai_briefing.log 2>&1
```

## 배포 옵션

### 옵션 A: 이메일 발송 추가
스크립트 끝에 이메일 발송 코드를 추가하면 됩니다:

```python
# Gmail SMTP 예시
import smtplib
from email.mime.text import MIMEText

def send_email(html_content, to_emails):
    msg = MIMEText(html_content, 'html')
    msg['Subject'] = f'AI Daily Briefing — {get_today_str()}'
    msg['From'] = 'your@gmail.com'
    msg['To'] = ', '.join(to_emails)

    with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
        server.login('your@gmail.com', 'app-password')
        server.send_message(msg)
```

### 옵션 B: GitHub Pages 자동 게시
GitHub Actions로 매일 빌드 후 Pages에 배포:

```yaml
# .github/workflows/daily-briefing.yml
name: AI Daily Briefing
on:
  schedule:
    - cron: '0 22 * * *'  # UTC 22시 = KST 07시
  workflow_dispatch:       # 수동 실행도 가능

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - run: pip install anthropic
      - run: python ai_daily_briefing.py
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
      - run: cp output/ai_briefing_*.html docs/index.html
      - uses: peaceiris/actions-gh-pages@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          publish_dir: ./docs
```

### 옵션 C: Slack/Discord 웹훅
생성된 HTML의 텍스트 버전을 Slack으로 보내기:

```python
import requests

def post_to_slack(news_data, webhook_url):
    blocks = [{"type": "header", "text": {
        "type": "plain_text",
        "text": f"🤖 AI Daily Briefing — {news_data['date']}"
    }}]
    for item in news_data['news']:
        blocks.append({"type": "section", "text": {
            "type": "mrkdwn",
            "text": f"*{item['number']}. {item['title']}*\n{item['insight']}"
        }})
    requests.post(webhook_url, json={"blocks": blocks})
```

## 커스터마이징

### 뉴스 주제 변경
`collect_and_analyze_news()` 함수의 system_prompt를 수정하세요.
예: "AI" → "AI + 블록체인", "ESG + AI" 등으로 확장 가능

### 모델 변경
- `claude-sonnet-4-6`: 가성비 최고 (기본 추천)
- `claude-opus-4-6`: 더 깊은 분석이 필요할 때 (비용 ~5x)
- `claude-haiku-4-5`: 비용 최소화 (품질 약간 낮음)

### HTML 디자인 변경
`generate_html()` 함수의 CSS를 수정하면 됩니다.
다크 테마 → 라이트 테마 전환도 CSS 변수만 바꾸면 OK.

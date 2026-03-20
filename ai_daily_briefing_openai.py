"""
AI Daily Briefing Generator (OpenAI 버전)
==========================================
OpenAI Responses API의 web_search_preview 도구를 활용해 AI 뉴스를 자동 수집하고
HTML 뉴스레터를 생성하는 반자동화 스크립트

사용법:
  1. pip install openai
  2. export OPENAI_API_KEY="your-api-key"
  3. python ai_daily_briefing_openai.py
  4. output/ 디렉토리에 HTML 파일 생성됨

비용 추정 (1회 실행):
  - gpt-4o: 입력 ~5K + 출력 ~4K ≈ $0.04~$0.07
  - Web Search: 검색당 $0.03 × ~5회 = $0.15
  - 총 1회 실행 비용: 약 $0.19~$0.22 (≈ 270~310원)
"""

import json
import os
import re
from datetime import datetime
from pathlib import Path

import openai


# ============================================================
# 설정
# ============================================================
MODEL = "o4-mini"
MAX_TOKENS = 8192
OUTPUT_DIR = Path("output")
ISU_CONTEXT_PATH = Path("ISU_COMPANY.md")


def load_isu_context() -> str:
    """이수시스템 컨텍스트 로드"""
    if ISU_CONTEXT_PATH.exists():
        return ISU_CONTEXT_PATH.read_text(encoding="utf-8")
    return ""


def get_today_str() -> str:
    """오늘 날짜 문자열"""
    now = datetime.now()
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    return f"{now.strftime('%Y.%m.%d')} ({weekdays[now.weekday()]})"


def get_file_date() -> str:
    return datetime.now().strftime("%Y_%m_%d")


# ============================================================
# Step 1: OpenAI Responses API + Web Search로 뉴스 수집 & 분석
# ============================================================
def collect_and_analyze_news(client: openai.OpenAI) -> str:
    """
    OpenAI Responses API에 web_search_preview 도구를 주고,
    AI 뉴스를 직접 검색 + 분석하게 함.
    """

    today = get_today_str()
    isu_context = load_isu_context()

    system_prompt = f"""당신은 AI 산업 전문 뉴스레터 에디터입니다.
오늘은 {today}입니다.

목표: 오늘/최근의 AI 관련 주요 뉴스 5개를 선별하고 분석합니다.

대상 독자:
- AI에 관심은 있지만 너무 바빠서 뉴스를 못 보는 직장인
- 기술적 깊이보다는 "그래서 나한테 뭐가 달라지는데?"를 궁금해하는 사람

뉴스 선별 기준 (중요도 순):
1. 새로운 AI 모델/제품 출시 (GPT, Claude, Gemini 등)
2. 빅테크의 AI 전략 변화 (구조조정, 투자, 인수합병)
3. AI가 실제 업무/산업에 미치는 영향
4. AI 규제/정책 변화
5. AI 연구 브레이크스루

각 뉴스에 반드시 포함할 것:
- 카테고리 태그 (모델 릴리스 / 제품 업데이트 / 일자리·사회 / 산업 동향 / 글로벌 이슈 중 택1)
- 제목 (한국어, 임팩트 있게)
- 본문 요약 (2~3문단, 핵심 숫자/사실 포함)
- 시사점 (독자가 실제로 행동할 수 있는 인사이트)

최종 출력 형식 (반드시 이 JSON 형식으로):
```json
{{
  "date": "{today}",
  "one_liner": "오늘의 AI를 한 문장으로 요약",
  "news": [
    {{
      "number": 1,
      "category": "모델 릴리스",
      "title": "뉴스 제목",
      "body": "본문 요약. 핵심 키워드는 **별표두개**로 감싸서 강조. 큰따옴표 대신 작은따옴표 사용.",
      "insight": "시사점",
      "isu_area": "AI 사업",
      "isu_tag": "[핵심 기회]",
      "isu_insight": "이수시스템 관점 인사이트"
    }}
  ],
  "takeaways": [
    "핵심 테이크어웨이 1 (**별표두개**로 강조 가능)",
    "핵심 테이크어웨이 2",
    "핵심 테이크어웨이 3"
  ],
  "isu_summary": "이수시스템 관점의 오늘 AI 뉴스 종합 인사이트 (2~3문장)"
}}
```

중요 규칙:
- JSON 문자열 값 안에서 큰따옴표(")를 절대 사용하지 마세요. 작은따옴표(')를 쓰세요.
- HTML 태그를 사용하지 마세요. 강조는 **별표두개**만 사용하세요.
- JSON이 유효한지 반드시 확인 후 출력하세요.

웹 검색을 적극적으로 활용해 최신 정보를 확보하세요.
오래된 정보가 아닌 오늘/이번 주의 뉴스를 우선하세요.

--- 이수시스템 컨텍스트 ---
{isu_context}

각 뉴스에 isu_area, isu_tag, isu_insight 필드를 추가하고,
마지막에 isu_summary로 이수시스템 관점 종합 인사이트를 작성하라.
isu_area는 6대 영역(AI 사업 / 디지털서비스 사업 / ESG 사업 / HR 사업 / 안전 사업 / 클라우드 사업) 중 가장 연관도 높은 것 1개 선택.
isu_tag는 [핵심 기회] [제품 강화] [영업 기회] [리스크] [모니터링] [정부 사업] 중 1개."""

    response = client.responses.create(
        model=MODEL,
        instructions=system_prompt,
        input=f"오늘({today}) 기준으로 AI 분야의 가장 중요한 뉴스 5개를 웹에서 검색하고, 분석해서 JSON으로 정리해줘.",
        tools=[{"type": "web_search_preview"}],
        max_output_tokens=MAX_TOKENS,
    )

    raw = response.output_text
    # OpenAI web_search 출처 주석 제거 (【1†source】 형태)
    raw = re.sub(r'【\d+†[^】]*】', '', raw)
    return raw


# ============================================================
# Step 2: JSON 파싱
# ============================================================
def parse_news_json(raw_text: str) -> dict:
    """응답에서 JSON 추출 (견고한 파싱)"""

    # ```json ... ``` 블록 찾기
    json_match = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # 블록 없으면 전체에서 { ... } 찾기 (가장 바깥 중괄호)
        depth = 0
        start = -1
        for i, ch in enumerate(raw_text):
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and start != -1:
                    json_str = raw_text[start:i+1]
                    break
        else:
            raise ValueError("JSON을 찾을 수 없습니다. 응답을 확인하세요.")

    json_str = fix_json_string(json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"  ⚠️ 1차 파싱 실패: {e}")
        print("  🔧 OpenAI에게 JSON 수정 요청 중...")
        return fix_json_with_openai(raw_text)


def fix_json_string(json_str: str) -> str:
    """흔한 JSON 깨짐 패턴 자동 수정"""
    lines = json_str.split('\n')
    json_str = '\n'.join(lines)

    json_str = re.sub(
        r'<(\w+)\s+(\w+)="([^"]*)"',
        r'<\1 \2=\'\3\'',
        json_str
    )

    json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)
    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)

    return json_str


def fix_json_with_openai(raw_text: str) -> dict:
    """파싱 실패 시 OpenAI에게 JSON 수정 요청 (fallback)"""
    client = openai.OpenAI()
    truncated = raw_text[:8000] if len(raw_text) > 8000 else raw_text

    response = client.responses.create(
        model=MODEL,
        input=f"""아래 텍스트에서 JSON 부분을 추출하고, 문법 오류를 수정해서
올바른 JSON만 출력해줘. 다른 설명 없이 JSON만 출력해.

원본 텍스트:
{truncated}""",
        max_output_tokens=MAX_TOKENS,
    )

    fixed_text = response.output_text

    json_match = re.search(r"```json\s*(.*?)\s*```", fixed_text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(1))

    json_match = re.search(r"\{.*\}", fixed_text, re.DOTALL)
    if json_match:
        return json.loads(json_match.group(0))

    raise ValueError("JSON 복구에 실패했습니다. output/ 폴더의 raw 파일을 확인하세요.")


# ============================================================
# Step 3: HTML 생성 (Anthropic 버전과 동일)
# ============================================================
def md_to_html(text: str) -> str:
    """**마크다운 강조**를 <strong>HTML</strong>로 변환"""
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)


def generate_html(data: dict) -> str:
    """뉴스 데이터로 HTML 뉴스레터 생성"""

    category_tags = {
        "모델 릴리스": ("tag-model", "#4488ff"),
        "제품 업데이트": ("tag-product", "#00e5a0"),
        "일자리·사회": ("tag-society", "#ff4488"),
        "산업 동향": ("tag-industry", "#ff8844"),
        "글로벌 이슈": ("tag-insight", "#ffcc00"),
    }

    news_sections = ""
    for item in data["news"]:
        cat = item.get("category", "산업 동향")
        tag_class, _ = category_tags.get(cat, ("tag-industry", "#ff8844"))
        isu_area = item.get("isu_area", "")
        isu_tag = item.get("isu_tag", "")
        isu_insight = item.get("isu_insight", "")

        isu_box = ""
        if isu_area or isu_insight:
            isu_box = f"""
    <div class="isu-box">
      <div class="isu-label">
        <span class="isu-area-tag">{isu_area}</span>
        <span class="isu-opp-tag">{isu_tag}</span>
      </div>
      <p>{isu_insight}</p>
    </div>"""

        news_sections += f"""
  <section class="section">
    <div class="section-header">
      <span class="section-number">{item['number']:02d}</span>
      <span class="section-tag {tag_class}">{cat}</span>
    </div>
    <h3 class="news-title">{item['title']}</h3>
    <p class="news-body">{md_to_html(item['body'])}</p>
    <div class="insight-box">
      <div class="label">시사점</div>
      <p>{md_to_html(item['insight'])}</p>
    </div>{isu_box}
  </section>"""

    takeaway_items = ""
    for t in data.get("takeaways", []):
        takeaway_items += f"\n      <li>{md_to_html(t)}</li>"

    # ISU 종합 인사이트 섹션
    isu_summary = data.get("isu_summary", "")
    isu_summary_section = ""
    if isu_summary:
        isu_summary_section = f"""
  <div class="isu-section">
    <h2>이수시스템 인사이트</h2>
    <p>{isu_summary}</p>
  </div>"""

    html = f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Daily Briefing — {data['date']}</title>
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@300;400;500;700;900&family=Playfair+Display:wght@700;900&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {{
    --bg: #0a0a0f;
    --surface: #12121a;
    --surface-2: #1a1a26;
    --accent: #00e5a0;
    --accent-dim: rgba(0,229,160,0.12);
    --accent-glow: rgba(0,229,160,0.25);
    --text: #e8e8ed;
    --text-dim: #8888a0;
    --text-muted: #555568;
    --orange: #ff8844;
    --blue: #4488ff;
    --pink: #ff4488;
    --yellow: #ffcc00;
    --border: rgba(255,255,255,0.06);
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    background: var(--bg);
    color: var(--text);
    font-family: 'Noto Sans KR', sans-serif;
    font-weight: 400;
    line-height: 1.75;
    min-height: 100vh;
  }}
  .container {{ max-width: 720px; margin: 0 auto; padding: 0 24px; }}
  .header {{
    padding: 60px 0 40px;
    border-bottom: 1px solid var(--border);
    position: relative;
    overflow: hidden;
  }}
  .header::before {{
    content: '';
    position: absolute;
    top: -100px; right: -100px;
    width: 300px; height: 300px;
    background: radial-gradient(circle, var(--accent-glow) 0%, transparent 70%);
    pointer-events: none;
    animation: pulse 4s ease-in-out infinite;
  }}
  @keyframes pulse {{ 0%, 100% {{ opacity: 0.3; }} 50% {{ opacity: 0.6; }} }}
  .header-top {{ display: flex; align-items: center; gap: 12px; margin-bottom: 20px; }}
  .logo-mark {{
    width: 36px; height: 36px;
    background: var(--accent);
    border-radius: 8px;
    display: flex; align-items: center; justify-content: center;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500; font-size: 14px; color: var(--bg);
  }}
  .brand-name {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px; font-weight: 500;
    color: var(--text-dim);
    letter-spacing: 2px; text-transform: uppercase;
  }}
  .header h1 {{
    font-family: 'Playfair Display', serif;
    font-size: 42px; font-weight: 900; line-height: 1.15;
    margin-bottom: 12px;
    background: linear-gradient(135deg, var(--text) 0%, var(--accent) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }}
  .date-line {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px; color: var(--text-muted);
    display: flex; align-items: center; gap: 12px;
  }}
  .date-line .dot {{
    width: 6px; height: 6px;
    background: var(--accent); border-radius: 50%;
    animation: blink 2s ease-in-out infinite;
  }}
  @keyframes blink {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.3; }} }}
  .tldr {{ padding: 32px 0; border-bottom: 1px solid var(--border); }}
  .tldr-label {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; color: var(--accent);
    letter-spacing: 3px; text-transform: uppercase;
    margin-bottom: 12px;
  }}
  .tldr p {{ font-size: 17px; font-weight: 500; line-height: 1.8; }}
  .section {{ padding: 40px 0; border-bottom: 1px solid var(--border); }}
  .section:last-child {{ border-bottom: none; }}
  .section-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 28px; }}
  .section-number {{
    font-family: 'Playfair Display', serif;
    font-size: 28px; font-weight: 900; color: var(--accent); line-height: 1;
  }}
  .section-tag {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; letter-spacing: 2px; text-transform: uppercase;
    padding: 4px 10px; border-radius: 4px; font-weight: 500;
  }}
  .tag-model {{ background: rgba(68,136,255,0.15); color: var(--blue); }}
  .tag-product {{ background: rgba(0,229,160,0.12); color: var(--accent); }}
  .tag-society {{ background: rgba(255,68,136,0.15); color: var(--pink); }}
  .tag-industry {{ background: rgba(255,136,68,0.15); color: var(--orange); }}
  .tag-insight {{ background: rgba(255,204,0,0.15); color: var(--yellow); }}
  .news-title {{ font-size: 22px; font-weight: 700; line-height: 1.4; margin-bottom: 16px; }}
  .news-body {{
    font-size: 15px; line-height: 1.85; margin-bottom: 16px; font-weight: 300;
  }}
  .news-body strong {{ color: var(--accent); font-weight: 500; }}
  .insight-box {{
    background: var(--surface-2);
    border-left: 3px solid var(--accent);
    padding: 16px 20px; border-radius: 0 8px 8px 0; margin-top: 16px;
  }}
  .insight-box .label {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; color: var(--accent);
    letter-spacing: 2px; text-transform: uppercase; margin-bottom: 8px;
  }}
  .insight-box p {{ font-size: 14px; line-height: 1.75; font-weight: 400; }}
  .isu-box {{
    background: rgba(255,136,68,0.08);
    border-left: 3px solid var(--orange);
    padding: 10px 14px; border-radius: 0 6px 6px 0; margin-top: 12px;
  }}
  .isu-box .isu-label {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; color: var(--orange);
    letter-spacing: 2px; text-transform: uppercase; margin-bottom: 6px;
  }}
  .isu-area-tag {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; padding: 2px 8px; border-radius: 3px;
    background: rgba(255,136,68,0.15); color: var(--orange);
    margin-right: 6px;
  }}
  .isu-opp-tag {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px; padding: 2px 8px; border-radius: 3px;
    background: rgba(255,204,0,0.15); color: var(--yellow);
  }}
  .isu-section {{
    padding: 40px 0; border-top: 2px solid var(--orange); margin-top: 20px;
  }}
  .isu-section h2 {{
    font-family: 'Playfair Display', serif;
    font-size: 24px; font-weight: 700; margin-bottom: 16px; color: var(--orange);
  }}
  .isu-section p {{ font-size: 15px; line-height: 1.85; font-weight: 300; }}
  .bottom-line {{
    padding: 40px 0; border-top: 2px solid var(--accent); margin-top: 20px;
  }}
  .bottom-line h2 {{
    font-family: 'Playfair Display', serif;
    font-size: 24px; font-weight: 700; margin-bottom: 20px; color: var(--accent);
  }}
  .bottom-line p {{ font-size: 15px; line-height: 1.85; font-weight: 300; margin-bottom: 12px; }}
  .action-list {{ list-style: none; margin-top: 20px; }}
  .action-list li {{
    position: relative; padding: 10px 0 10px 24px;
    font-size: 14px; font-weight: 400; line-height: 1.7;
  }}
  .action-list li::before {{
    content: '→'; position: absolute; left: 0;
    color: var(--accent); font-family: 'JetBrains Mono', monospace; font-weight: 500;
  }}
  .action-list li strong {{ color: var(--accent); font-weight: 500; }}
  .footer {{
    padding: 40px 0; text-align: center;
    color: var(--text-muted); font-size: 12px;
    font-family: 'JetBrains Mono', monospace;
    border-top: 1px solid var(--border);
  }}
  .footer .accent {{ color: var(--accent); }}
  @media (max-width: 600px) {{
    .header h1 {{ font-size: 30px; }}
    .news-title {{ font-size: 19px; }}
    .container {{ padding: 0 16px; }}
    .header {{ padding: 40px 0 30px; }}
  }}
</style>
</head>
<body>
<div class="container">
  <header class="header">
    <div class="header-top">
      <div class="logo-mark">AI</div>
      <span class="brand-name">Daily Briefing</span>
    </div>
    <h1>오늘의 AI, 3분 안에 끝내기</h1>
    <div class="date-line">
      <span class="dot"></span>
      <span>{data['date']} — 바쁜 당신을 위한 AI 핵심 브리핑</span>
    </div>
  </header>

  <div class="tldr">
    <div class="tldr-label">오늘의 한 줄</div>
    <p>{data['one_liner']}</p>
  </div>

  {news_sections}
  {isu_summary_section}

  <div class="bottom-line">
    <h2>오늘의 핵심 테이크어웨이</h2>
    <ul class="action-list">{takeaway_items}
    </ul>
  </div>

  <footer class="footer">
    <p>AI Daily Briefing — <span class="accent">바쁜 사람을 위한 3분 AI 뉴스</span></p>
    <p style="margin-top: 8px;">{data['date']} | 매일 아침 업데이트</p>
    <p style="margin-top: 8px;">© keyboard@kakao.com</p>
  </footer>
</div>
</body>
</html>"""

    return html


# ============================================================
# Step 4: 메인 실행
# ============================================================
def main():
    print("=" * 60)
    print(f"  AI Daily Briefing Generator (OpenAI)")
    print(f"  {get_today_str()}")
    print("=" * 60)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("\n❌ OPENAI_API_KEY 환경변수를 설정하세요.")
        print("   export OPENAI_API_KEY='your-api-key'")
        return

    client = openai.OpenAI(api_key=api_key)

    # Step 1: 뉴스 수집 & 분석
    print("\n🔍 AI 뉴스 검색 및 분석 중...")
    raw_response = collect_and_analyze_news(client)

    # 원본 응답 저장 (디버깅용)
    OUTPUT_DIR.mkdir(exist_ok=True)
    raw_path = OUTPUT_DIR / f"ai_briefing_{get_file_date()}_raw.txt"
    raw_path.write_text(raw_response, encoding="utf-8")
    print(f"   📄 원본 응답 저장: {raw_path}")

    # Step 2: JSON 파싱
    print("📋 뉴스 데이터 파싱 중...")
    try:
        news_data = parse_news_json(raw_response)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"\n❌ JSON 파싱 최종 실패: {e}")
        print(f"   원본 응답은 {raw_path} 에서 확인하세요.")
        return

    print(f"   ✅ {len(news_data.get('news', []))}개 뉴스 수집 완료")

    # Step 3: HTML 생성
    print("🎨 HTML 뉴스레터 생성 중...")
    html = generate_html(news_data)

    OUTPUT_DIR.mkdir(exist_ok=True)
    filename = f"ai_briefing_{get_file_date()}.html"
    filepath = OUTPUT_DIR / filename
    filepath.write_text(html, encoding="utf-8")

    print(f"\n✅ 완료! 파일 저장됨: {filepath}")
    print(f"   브라우저에서 열기: open {filepath}")

    json_path = OUTPUT_DIR / f"ai_briefing_{get_file_date()}.json"
    json_path.write_text(
        json.dumps(news_data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"   JSON 원본: {json_path}")


if __name__ == "__main__":
    main()

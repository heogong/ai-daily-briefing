"""
briefing_core.py — AI Daily Briefing 공통 로직
================================================
API 클라이언트에 의존하지 않는 모든 공통 코드:
  - RSS 수집 / 기사 파싱
  - 시스템 프롬프트 빌더
  - JSON 파싱 (fix_fn 주입 방식)
  - TTS 생성
  - HTML 렌더링
"""

import feedparser
import json
import requests
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path


# ============================================================
# 설정
# ============================================================
MAX_TOKENS = 8192
OUTPUT_DIR = Path("output")
ISU_CONTEXT_PATH = Path("ISU_COMPANY.md")
KST = timezone(timedelta(hours=9))
RSS_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def load_isu_context() -> str:
    if ISU_CONTEXT_PATH.exists():
        return ISU_CONTEXT_PATH.read_text(encoding="utf-8")
    return ""


# ============================================================
# 날짜 / 시간 유틸
# ============================================================
def _kst_now() -> datetime:
    return datetime.now(tz=KST)


def get_news_window_str() -> str:
    now = _kst_now()
    since = now - timedelta(hours=24)
    return (f"{since.strftime('%Y년 %m월 %d일 %H:%M')} ~ "
            f"{now.strftime('%Y년 %m월 %d일 %H:%M')} (KST)")


def get_today_str() -> str:
    now = _kst_now()
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    return f"{now.strftime('%Y.%m.%d')} ({weekdays[now.weekday()]})"


def get_file_date() -> str:
    return _kst_now().strftime("%Y_%m_%d")


# ============================================================
# Step 1: RSS 피드 수집
# ============================================================
def _rss_feeds_with_date() -> list[str]:
    yesterday = (_kst_now() - timedelta(hours=24)).strftime("%Y-%m-%d")
    return [
        f"https://news.google.com/rss/search?q=artificial+intelligence+LLM+after:{yesterday}&hl=en&gl=US&ceid=US:en",
        f"https://news.google.com/rss/search?q=OpenAI+Anthropic+Google+Gemini+after:{yesterday}&hl=en&gl=US&ceid=US:en",
        f"https://news.google.com/rss/search?q=인공지능+AI+LLM+after:{yesterday}&hl=ko&gl=KR&ceid=KR:ko",
        "https://techcrunch.com/tag/artificial-intelligence/feed/",
        "https://venturebeat.com/ai/feed/",
        "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml",
    ]


def _it_company_rss_feeds_with_date() -> list[str]:
    yesterday = (_kst_now() - timedelta(hours=24)).strftime("%Y-%m-%d")
    return [
        f"https://news.google.com/rss/search?q=국내+IT+기업+M%26A+인수합병+after:{yesterday}&hl=ko&gl=KR&ceid=KR:ko",
        f"https://news.google.com/rss/search?q=스타트업+투자+펀딩+시리즈+after:{yesterday}&hl=ko&gl=KR&ceid=KR:ko",
        f"https://news.google.com/rss/search?q=IT+기업+경영+인사+CEO+after:{yesterday}&hl=ko&gl=KR&ceid=KR:ko",
        f"https://news.google.com/rss/search?q=테크+기업+사업+전략+확장+after:{yesterday}&hl=ko&gl=KR&ceid=KR:ko",
        f"https://news.google.com/rss/search?q=국내+IT+기업+실적+시장동향+after:{yesterday}&hl=ko&gl=KR&ceid=KR:ko",
    ]


def _parse_entry_date(entry) -> datetime | None:
    for attr in ('published_parsed', 'updated_parsed', 'created_parsed'):
        val = getattr(entry, attr, None)
        if val:
            try:
                return datetime(*val[:6], tzinfo=timezone.utc)
            except Exception:
                continue
    return None


def _fetch_from_feeds(feeds: list[str], max_hours: int, retry_fn) -> list:
    """공통 RSS fetch 로직. retry_fn 은 max_hours 를 받아 재귀 호출하는 함수."""
    cutoff = _kst_now() - timedelta(hours=max_hours)
    articles = []
    seen_titles: set[str] = set()

    for url in feeds:
        try:
            try:
                resp = requests.get(url, headers={"User-Agent": RSS_USER_AGENT}, timeout=15)
            except requests.exceptions.SSLError:
                resp = requests.get(url, headers={"User-Agent": RSS_USER_AGENT}, timeout=15, verify=False)
            feed = feedparser.parse(resp.content)
            status = getattr(feed, 'status', 0)
            total = len(feed.entries)

            if status not in (0, 200, 301, 302) and status != 0:
                print(f"   ⚠️ HTTP {status}: {url[:60]}")
                continue

            within = 0
            no_date = 0
            for entry in feed.entries:
                published = _parse_entry_date(entry)

                if published is None:
                    no_date += 1
                    pub_str = _kst_now().strftime('%Y-%m-%d %H:%M KST')
                elif published < cutoff:
                    continue
                else:
                    within += 1
                    pub_str = published.astimezone(KST).strftime('%Y-%m-%d %H:%M KST')

                title = entry.get('title', '').strip()
                if not title or title in seen_titles:
                    continue
                seen_titles.add(title)

                summary = entry.get('summary', entry.get('description', ''))
                summary = re.sub(r'<[^>]+>', '', summary).strip()[:400]

                articles.append({
                    'title': title,
                    'summary': summary,
                    'link': entry.get('link', ''),
                    'published': pub_str,
                    'source': feed.feed.get('title', url.split('/')[2]),
                })

            print(f"   {url.split('/')[2][:40]:40s} 전체:{total:3d} | {max_hours}h이내:{within:3d} | 날짜없음:{no_date:2d}")

        except Exception as e:
            print(f"   ⚠️ RSS 피드 오류 ({url[:60]}): {e}")

    articles.sort(key=lambda x: x['published'], reverse=True)

    if len(articles) < 5 and max_hours < 72:
        extended = max_hours * 2
        print(f"   ⚠️ 기사 부족 ({len(articles)}개) → {extended}시간으로 범위 확장 재시도")
        return retry_fn(max_hours=extended)

    return articles


def fetch_rss_articles(max_hours: int = 24) -> list:
    return _fetch_from_feeds(_rss_feeds_with_date(), max_hours, fetch_rss_articles)


def fetch_it_company_articles(max_hours: int = 24) -> list:
    return _fetch_from_feeds(_it_company_rss_feeds_with_date(), max_hours, fetch_it_company_articles)


def format_articles_text(articles: list) -> str:
    text = ""
    for i, a in enumerate(articles, 1):
        text += f"\n[{i}] {a['published']} | {a['source']}\n제목: {a['title']}\n요약: {a['summary']}\n링크: {a['link']}\n"
    return text


# ============================================================
# Step 2: 시스템 프롬프트 빌더
# ============================================================
def build_ai_briefing_prompt(today: str, isu_context: str) -> str:
    return f"""당신은 AI 산업 전문 뉴스레터 에디터입니다.
오늘은 {today}입니다.

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
- 시사점: 업계 전반에 어떤 변화를 의미하는지, 독자가 알아야 할 맥락 (특정 회사 관점 아닌 해당 뉴스 시사점)

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
      "body": "본문 요약. 핵심 키워드는 **별표두개**로 강조. 큰따옴표 대신 작은따옴표 사용.",
      "insight": "이 뉴스가 업계 전반에 미치는 의미와 맥락 (이수시스템 언급 금지)",
      "isu_area": "AI 사업",
      "isu_tag": "[핵심 기회]",
      "isu_insight": "이수시스템 관점 인사이트",
      "url": "원문 기사 링크 (제공된 링크 그대로 사용)",
      "source": "출처명 (예: TechCrunch, VentureBeat, Google News)"
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
- insight 필드에는 이수시스템을 절대 언급하지 마세요. ISU 관련 내용은 오직 isu_insight에만 작성합니다.

--- 이수시스템 컨텍스트 ---
insight 필드는 기사 자체의 업계 시사점이므로 절대 수정하지 않는다. ISU 관점은 isu_insight와 isu_summary에만 작성한다.

{isu_context}

각 뉴스에 isu_area, isu_tag, isu_insight 필드를 추가하고,
마지막에 isu_summary로 이수시스템 관점 종합 인사이트를 작성하라.
isu_area는 6대 영역(AI 사업 / 디지털서비스 사업 / ESG 사업 / HR 사업 / 안전 사업 / 클라우드 사업) 중 가장 연관도 높은 것 1개 선택.
isu_tag는 [핵심 기회] [제품 강화] [영업 기회] [리스크] [모니터링] [정부 사업] 중 1개."""


def build_it_company_prompt(today: str) -> str:
    return f"""당신은 국내 IT 업계 동향 전문 뉴스레터 에디터입니다.
오늘은 {today}입니다.

대상 독자:
- 국내 IT/테크 산업 동향을 파악하려는 직장인
- M&A, 투자, 경영진 변화, 사업 전략 등 기업 움직임에 관심 있는 독자

뉴스 선별 기준 (중요도 순):
1. M&A·인수합병 (기업 간 인수, 합병, 지분 취득)
2. 투자·펀딩 (시리즈 투자, IPO, 전략적 투자)
3. 경영·인사 (CEO 교체, 임원 영입, 조직 개편)
4. 사업 전략 (신규 사업 진출, 파트너십, 사업 철수)
5. 시장 동향 (실적 발표, 시장 점유율, 업계 트렌드)

각 뉴스에 반드시 포함할 것:
- 카테고리 태그 (M&A·인수합병 / 투자·펀딩 / 경영·인사 / 사업 전략 / 시장 동향 중 택1)
- 제목 (한국어, 핵심 기업명과 이슈를 담아 임팩트 있게)
- 본문 요약 (2~3문단, 거래 규모·금액·날짜 등 핵심 숫자/사실 포함)
- 시사점: 해당 움직임이 업계에 미치는 의미와 맥락

최종 출력 형식 (반드시 이 JSON 형식으로):
```json
{{
  "date": "{today}",
  "one_liner": "오늘 국내 IT 업계를 한 문장으로 요약",
  "news": [
    {{
      "number": 1,
      "category": "M&A·인수합병",
      "title": "뉴스 제목",
      "body": "본문 요약. 핵심 키워드는 **별표두개**로 강조. 큰따옴표 대신 작은따옴표 사용.",
      "insight": "이 뉴스가 국내 IT 업계에 미치는 의미와 맥락",
      "url": "원문 기사 링크 (제공된 링크 그대로 사용)",
      "source": "출처명"
    }}
  ],
  "takeaways": [
    "핵심 테이크어웨이 1 (**별표두개**로 강조 가능)",
    "핵심 테이크어웨이 2",
    "핵심 테이크어웨이 3"
  ]
}}
```

중요 규칙:
- JSON 문자열 값 안에서 큰따옴표(")를 절대 사용하지 마세요. 작은따옴표(')를 쓰세요.
- HTML 태그를 사용하지 마세요. 강조는 **별표두개**만 사용하세요.
- JSON이 유효한지 반드시 확인 후 출력하세요."""


# ============================================================
# Step 2: JSON 파싱
# ============================================================
def fix_json_string(json_str: str) -> str:
    lines = json_str.split('\n')
    json_str = '\n'.join(lines)
    json_str = re.sub(r'<(\w+)\s+(\w+)="([^"]*)"', r'<\1 \2=\'\3\'', json_str)
    json_str = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', json_str)
    json_str = re.sub(r',\s*([\]}])', r'\1', json_str)
    return json_str


def parse_news_json(raw_text: str, fix_fn=None) -> dict:
    """LLM 응답에서 JSON 추출. 파싱 실패 시 fix_fn(raw_text) 호출."""
    json_match = re.search(r"```json\s*(.*?)\s*```", raw_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
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
            raise ValueError("JSON을 찾을 수 없습니다. 응답 원본을 확인하세요.")

    json_str = fix_json_string(json_str)

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print(f"  ⚠️ 1차 파싱 실패: {e}")
        if fix_fn:
            print("  🔧 JSON 수정 요청 중...")
            return fix_fn(raw_text)
        raise


# ============================================================
# Step 3: TTS 음성 생성
# ============================================================
_TTS_WORD_MAP = {
    r'\bWORKUP\b': '워크업',
    r'\bRAG\b': '레그',
    r'\bClaude\b': '클로드',
    r'\bOpenAI\b': '오픈에이아이',
}


def _strip_special(text: str) -> str:
    text = re.sub(r'\*+', '', text)
    text = re.sub(r'[#\[\](){}<>|\\^~`]', '', text)
    text = re.sub(r'https?://\S+', '', text)
    for pattern, replacement in _TTS_WORD_MAP.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _date_to_tts(date_str: str) -> str:
    weekday_map = {"월": "월요일", "화": "화요일", "수": "수요일",
                   "목": "목요일", "금": "금요일", "토": "토요일", "일": "일요일"}
    m = re.match(r'(\d{4})\.(\d{2})\.(\d{2})\s*\(([월화수목금토일])\)', date_str)
    if m:
        y, mo, d, wd = m.groups()
        return f"{y}년 {int(mo)}월 {int(d)}일 {weekday_map[wd]}"
    return date_str


def build_tts_text(news_data: dict) -> str:
    date_tts = _date_to_tts(news_data.get('date', ''))
    lines = [
        f"AI 데일리 브리핑, {date_tts}.",
        "바쁜 사람을 위한 오늘의 AI 뉴스를 전해드립니다.",
        "",
    ]
    for i, item in enumerate(news_data.get('news', []), 1):
        cat = _strip_special(item.get('category', ''))
        title = _strip_special(item.get('title', ''))
        body = _strip_special(item.get('body', ''))
        lines.append(f"뉴스 {i}번. {cat}.")
        lines.append(title)
        if body:
            lines.append(body)
        lines.append("")
    lines.append("이상 AI 데일리 브리핑이었습니다. 좋은 하루 되세요.")
    return "\n".join(lines)


def generate_tts_audio(text: str, api_key: str) -> bytes | None:
    import base64
    url = f"https://texttospeech.googleapis.com/v1/text:synthesize?key={api_key}"
    payload = {
        "input": {"text": text[:4900]},
        "voice": {"languageCode": "ko-KR", "name": "ko-KR-Wavenet-D"},
        "audioConfig": {"audioEncoding": "MP3"}
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            return base64.b64decode(resp.json()["audioContent"])
        print(f"   ⚠️ TTS API 오류 {resp.status_code}: {resp.text[:200]}")
    except Exception as e:
        print(f"   ⚠️ TTS 생성 실패: {e}")
    return None


# ============================================================
# Step 4: HTML 생성
# ============================================================
def md_to_html(text: str) -> str:
    return re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)


def generate_html(data: dict, it_data: dict = None, audio_filename=None) -> str:
    audio_tag = (
        f'<audio src="{audio_filename}" controls style="position:fixed;bottom:20px;'
        f'right:20px;z-index:100;width:260px;border-radius:12px;box-shadow:0 4px 16px rgba(0,0,0,0.5);"></audio>'
        if audio_filename else ""
    )

    category_tags = {
        "모델 릴리스":  ("tag-model",    "#4488ff"),
        "제품 업데이트": ("tag-product",  "#00e5a0"),
        "일자리·사회":  ("tag-society",  "#ff4488"),
        "산업 동향":    ("tag-industry", "#ff8844"),
        "글로벌 이슈":  ("tag-insight",  "#ffcc00"),
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

        url = item.get("url", "")
        source = item.get("source", "")
        source_link = ""
        if url:
            source_label = source if source else "원문 보기"
            source_link = f"""
    <div class="source-link"><a href="{url}" target="_blank" rel="noopener noreferrer">출처: {source_label} →</a></div>"""

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
    </div>{isu_box}{source_link}
  </section>"""

    takeaway_items = "".join(f"\n      <li>{md_to_html(t)}</li>" for t in data.get("takeaways", []))

    isu_summary = data.get("isu_summary", "")
    isu_summary_section = ""
    if isu_summary:
        isu_summary_section = f"""
  <div class="isu-section">
    <h2>이수시스템 인사이트</h2>
    <p>{isu_summary}</p>
  </div>"""

    it_category_tags = {
        "M&A·인수합병": "tag-industry",
        "투자·펀딩":    "tag-model",
        "경영·인사":    "tag-society",
        "사업 전략":    "tag-insight",
        "시장 동향":    "tag-product",
    }

    if it_data:
        it_news_sections = ""
        for item in it_data.get("news", []):
            cat = item.get("category", "시장 동향")
            tag_class = it_category_tags.get(cat, "tag-industry")
            url = item.get("url", "")
            source = item.get("source", "")
            source_link = ""
            if url:
                source_label = source if source else "원문 보기"
                source_link = f"""
    <div class="source-link"><a href="{url}" target="_blank" rel="noopener noreferrer">출처: {source_label} →</a></div>"""

            it_news_sections += f"""
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
    </div>{source_link}
  </section>"""

        it_takeaway_items = "".join(f"\n      <li>{md_to_html(t)}</li>" for t in it_data.get("takeaways", []))
        tab_it_content = f"""
  <div class="tldr">
    <div class="tldr-label">오늘의 한 줄</div>
    <p>{it_data.get('one_liner', '')}</p>
  </div>

  {it_news_sections}

  <div class="bottom-line">
    <h2>오늘의 핵심 테이크어웨이</h2>
    <ul class="action-list">{it_takeaway_items}
    </ul>
  </div>"""
    else:
        tab_it_content = """
    <div class="tab-empty">
      <div class="empty-icon">📊</div>
      <p>국내 IT 회사 동향 <span class="coming">준비 중</span></p>
      <p>M&amp;A · 투자 · 경영 · 경제 소식이 곧 업데이트됩니다</p>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Daily Briefing — {data['date']}</title>
<link rel="icon" type="image/svg+xml" href="favicon.svg">
<meta property="og:title" content="AI Daily Briefing — {data['date']}">
<meta property="og:description" content="바쁜 사람을 위한 3분 AI 뉴스">
<meta property="og:image" content="og-image.png">
<meta property="og:type" content="article">
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
    padding-bottom: 0;
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
    overflow-wrap: break-word; word-break: break-word;
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
  .source-link {{ margin-top: 10px; text-align: right; }}
  .source-link a {{ font-size: 12px; color: var(--text-muted); text-decoration: none; }}
  .source-link a:hover {{ color: var(--text-dim); }}
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
  .tab-nav {{
    display: flex;
    gap: 0;
    border-bottom: 2px solid var(--border);
    margin-top: 8px;
  }}
  .tab-btn {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px; letter-spacing: 1.5px; text-transform: uppercase;
    padding: 16px 20px;
    background: none; border: none;
    border-bottom: 2px solid transparent;
    margin-bottom: -2px;
    color: var(--text-muted);
    cursor: pointer;
    transition: color 0.2s, border-color 0.2s;
    white-space: nowrap;
  }}
  .tab-btn.active {{ color: var(--accent); border-bottom-color: var(--accent); }}
  .tab-btn:hover:not(.active) {{ color: var(--text-dim); }}
  .tab-pane {{ display: none; }}
  .tab-pane.active {{ display: block; }}
  .tab-empty {{
    padding: 80px 0; text-align: center;
    color: var(--text-muted);
    font-family: 'JetBrains Mono', monospace; font-size: 13px;
  }}
  .tab-empty .empty-icon {{ font-size: 36px; margin-bottom: 16px; opacity: 0.3; }}
  .tab-empty p {{ line-height: 2; }}
  .tab-empty .coming {{ color: var(--accent); }}
  @media (max-width: 600px) {{
    .header h1 {{ font-size: 30px; }}
    .news-title {{ font-size: 19px; }}
    .container {{ padding: 0 16px; }}
    .header {{ padding: 40px 0 30px; }}
    .tab-btn {{ font-size: 10px; padding: 14px 14px; letter-spacing: 1px; }}
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
    <h1 id="main-title">오늘의 AI, 3분 안에 끝내기</h1>
    <div class="date-line">
      <span class="dot"></span>
      <span>{data['date']} — 바쁜 당신을 위한 AI 핵심 브리핑</span>
    </div>
  </header>

  <nav class="tab-nav">
    <button class="tab-btn active" onclick="switchTab(this,'tab-ai')">오늘의 AI 브리핑</button>
    <button class="tab-btn" onclick="switchTab(this,'tab-it')">국내 IT 회사 동향</button>
  </nav>

  <div id="tab-ai" class="tab-pane active">
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
  </div><!-- /tab-ai -->

  <div id="tab-it" class="tab-pane">{tab_it_content}
  </div><!-- /tab-it -->

  <footer class="footer">
    <p>AI Daily Briefing — <span class="accent">바쁜 사람을 위한 3분 AI 뉴스</span></p>
    <p style="margin-top: 8px;">{data['date']} | 매일 아침 업데이트</p>
    <p style="margin-top: 8px;">© keyboard@kakao.com</p>
  </footer>
</div>
{audio_tag}
<script>
  const TAB_TITLES = {{
    'tab-ai': '오늘의 AI, 3분 안에 끝내기',
    'tab-it': '국내 IT 회사 동향'
  }};
  function switchTab(btn, id) {{
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(id).classList.add('active');
    document.getElementById('main-title').textContent = TAB_TITLES[id];
    const audio = document.querySelector('audio');
    if (audio) {{
      if (id === 'tab-it') {{
        audio.pause();
        audio.style.display = 'none';
      }} else {{
        audio.style.display = '';
      }}
    }}
  }}
</script>
</body>
</html>"""

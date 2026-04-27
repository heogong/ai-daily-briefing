"""
AI Daily Briefing Generator — OpenAI API
==========================================
사용법:
  1. pip install openai feedparser requests
  2. export OPENAI_API_KEY="your-api-key"
  3. python ai_daily_briefing_openai.py
  4. output/ 디렉토리에 HTML 파일 생성됨
"""

import openai
import json
import os
import re

from briefing_core import (
    MAX_TOKENS, OUTPUT_DIR,
    load_isu_context, get_today_str, get_news_window_str, get_file_date,
    fetch_rss_articles, fetch_it_company_articles, format_articles_text,
    build_ai_briefing_prompt, build_it_company_prompt,
    parse_news_json, inject_article_urls,
    build_tts_text, generate_tts_audio,
    generate_html,
)

MODEL = "o4-mini"


# ============================================================
# OpenAI API 전용: 뉴스 분석
# ============================================================
def collect_and_analyze_news(client: openai.OpenAI) -> tuple[str, list]:
    today = get_today_str()
    news_window = get_news_window_str()
    isu_context = load_isu_context()

    print("   📡 RSS 피드 수집 중...")
    articles = fetch_rss_articles()
    print(f"   ✅ {len(articles)}개 기사 수집 ({news_window})")
    if not articles:
        raise ValueError("RSS에서 수집된 기사가 없습니다.")

    system_prompt = build_ai_briefing_prompt(today, isu_context)
    user_message = (
        f"아래는 {news_window} 사이에 RSS 피드에서 수집한 AI 뉴스 {len(articles)}개입니다.\n"
        f"이 중에서 가장 중요한 5개를 선별하고, 각 뉴스를 분석해서 JSON으로 정리해주세요.\n\n"
        f"선별 조건: **대한민국 AI 산업 관련 기사를 반드시 1개 이상 포함**하세요. "
        f"한국 기사가 없거나 부족할 경우, 나머지 중 가장 중요한 기사로 채워도 됩니다.\n\n"
        f"{format_articles_text(articles)}"
    )

    response = client.responses.create(
        model=MODEL,
        instructions=system_prompt,
        input=user_message,
        max_output_tokens=MAX_TOKENS,
    )
    return response.output_text, articles


def analyze_it_company_news(client: openai.OpenAI, articles: list) -> tuple[str, list]:
    today = get_today_str()
    news_window = get_news_window_str()

    if not articles:
        raise ValueError("IT 기업 동향 기사가 없습니다.")

    system_prompt = build_it_company_prompt(today)
    user_message = (
        f"아래는 {news_window} 사이에 RSS 피드에서 수집한 국내 IT 기업 동향 기사 {len(articles)}개입니다.\n"
        f"이 중에서 가장 중요한 5개를 선별하고, 각 뉴스를 분석해서 JSON으로 정리해주세요.\n\n"
        f"{format_articles_text(articles)}"
    )

    response = client.responses.create(
        model=MODEL,
        instructions=system_prompt,
        input=user_message,
        max_output_tokens=MAX_TOKENS,
    )
    return response.output_text, articles


def fix_json_with_openai(raw_text: str) -> dict:
    """파싱 실패 시 OpenAI에게 JSON 수정 요청 (fallback)"""
    client = openai.OpenAI()
    truncated = raw_text[:8000]
    response = client.responses.create(
        model=MODEL,
        input=(
            "아래 텍스트에서 JSON 부분을 추출하고, 문법 오류를 수정해서 "
            "올바른 JSON만 출력해줘. 다른 설명 없이 JSON만 출력해.\n\n"
            f"원본 텍스트:\n{truncated}"
        ),
        max_output_tokens=MAX_TOKENS,
    )
    fixed_text = response.output_text

    m = re.search(r"```json\s*(.*?)\s*```", fixed_text, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    m = re.search(r"\{.*\}", fixed_text, re.DOTALL)
    if m:
        return json.loads(m.group(0))
    raise ValueError("JSON 복구에 실패했습니다. output/ 폴더의 raw 파일을 확인하세요.")


# ============================================================
# 메인 실행
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

    # Step 1: AI 뉴스 수집 & 분석
    print("\n🔍 AI 뉴스 검색 및 분석 중...")
    raw_response, ai_articles = collect_and_analyze_news(client)

    OUTPUT_DIR.mkdir(exist_ok=True)
    raw_path = OUTPUT_DIR / f"ai_briefing_{get_file_date()}_raw.txt"
    raw_path.write_text(raw_response, encoding="utf-8")
    print(f"   📄 원본 응답 저장: {raw_path}")

    # Step 2: JSON 파싱 + URL 주입
    print("📋 뉴스 데이터 파싱 중...")
    try:
        news_data = parse_news_json(raw_response, fix_fn=fix_json_with_openai)
        news_data = inject_article_urls(news_data, ai_articles)
    except (json.JSONDecodeError, ValueError) as e:
        print(f"\n❌ JSON 파싱 최종 실패: {e}")
        print(f"   원본 응답은 {raw_path} 에서 확인하세요.")
        return
    print(f"   ✅ {len(news_data.get('news', []))}개 뉴스 수집 완료")

    # Step 3: TTS 음성 생성 (선택적)
    audio_filename = None
    tts_api_key = os.environ.get("GCP_TTS_KEY")
    if tts_api_key:
        print("🔊 TTS 음성 생성 중...")
        audio_bytes = generate_tts_audio(build_tts_text(news_data), tts_api_key)
        if audio_bytes:
            audio_filename = f"ai_briefing_{get_file_date()}.mp3"
            (OUTPUT_DIR / audio_filename).write_bytes(audio_bytes)
            print(f"   ✅ 음성 파일 저장: {OUTPUT_DIR / audio_filename}")
    else:
        print("   ⏭️ GCP_TTS_KEY 없음 — TTS 생략")

    # Step 4: 국내 IT 기업 동향 수집 & 분석
    print("\n🏢 국내 IT 기업 동향 수집 중...")
    it_data = None
    try:
        it_articles = fetch_it_company_articles()
        print(f"   ✅ {len(it_articles)}개 IT 기업 기사 수집")
        if it_articles:
            it_raw, it_articles = analyze_it_company_news(client, it_articles)
            it_raw_path = OUTPUT_DIR / f"it_company_{get_file_date()}_raw.txt"
            it_raw_path.write_text(it_raw, encoding="utf-8")
            it_data = parse_news_json(it_raw, fix_fn=fix_json_with_openai)
            it_data = inject_article_urls(it_data, it_articles)
            print(f"   ✅ {len(it_data.get('news', []))}개 IT 기업 뉴스 파싱 완료")
            (OUTPUT_DIR / f"it_company_{get_file_date()}.json").write_text(
                json.dumps(it_data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
    except Exception as e:
        print(f"   ⚠️ IT 기업 동향 수집 실패 (Tab 2 플레이스홀더로 표시): {e}")

    # Step 5: HTML 생성 & 저장
    print("🎨 HTML 뉴스레터 생성 중...")
    html = generate_html(news_data, it_data=it_data, audio_filename=audio_filename)
    filepath = OUTPUT_DIR / f"ai_briefing_{get_file_date()}.html"
    filepath.write_text(html, encoding="utf-8")
    print(f"\n✅ 완료! 파일 저장됨: {filepath}")
    print(f"   브라우저에서 열기: open {filepath}")

    json_path = OUTPUT_DIR / f"ai_briefing_{get_file_date()}.json"
    json_path.write_text(json.dumps(news_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"   JSON 원본: {json_path}")


if __name__ == "__main__":
    main()

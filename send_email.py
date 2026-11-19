"""
이메일 발송 스크립트
Gmail SMTP로 구독자 전원에게 AI Daily Briefing 발송

구독자 관리: subscribers.txt 파일에 이메일 한 줄에 하나씩
"""

import smtplib
import os
import json
import glob
import re
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timedelta, timezone
from pathlib import Path

KST = timezone(timedelta(hours=9))


def to_email_html(html: str) -> str:
    """웹용 HTML을 메일 클라이언트용으로 변환.

    메일 클라이언트는 <script>를 제거하므로 탭 전환이 동작하지 않는다.
    탭 네비게이션/오디오/스크립트를 제거하고 두 탭을 모두 펼쳐서 보여준다.
    """
    html = re.sub(r'<nav class="tab-nav">.*?</nav>', '', html, flags=re.DOTALL)
    html = re.sub(r'<script>.*?</script>', '', html, flags=re.DOTALL)
    html = re.sub(r'<audio\b[^>]*>.*?</audio>', '', html, flags=re.DOTALL)
    html = html.replace(
        '<div id="tab-ai" class="tab-pane active">',
        '<div id="tab-ai" class="tab-pane active" style="display:block;">',
    )
    html = html.replace(
        '<div id="tab-it" class="tab-pane">',
        '<div id="tab-it" class="tab-pane active" style="display:block;">'
        '<h2 style="margin:48px 0 8px;padding-top:32px;border-top:1px solid #333;">'
        '국내 IT 회사 동향</h2>',
    )
    return html


def get_subscribers() -> list[str]:
    """subscribers.txt에서 구독자 이메일 목록 로드"""
    path = Path("subscribers.txt")
    if not path.exists():
        print("⚠️ subscribers.txt 파일이 없습니다.")
        return []

    emails = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        # 빈 줄, 주석(#) 무시
        if line and not line.startswith("#"):
            emails.append(line)

    return emails


def get_latest_briefing() -> tuple[str, str]:
    """최신 HTML 브리핑과 JSON 요약 로드"""
    html_files = sorted(glob.glob("output/ai_briefing_*.html"), reverse=True)
    json_files = sorted(glob.glob("output/ai_briefing_*.json"), reverse=True)

    if not html_files:
        raise FileNotFoundError("output/ 폴더에 HTML 파일이 없습니다.")

    html_content = to_email_html(Path(html_files[0]).read_text(encoding="utf-8"))

    one_liner = ""
    if json_files:
        try:
            data = json.loads(Path(json_files[0]).read_text(encoding="utf-8"))
            one_liner = data.get("one_liner", "")
        except (json.JSONDecodeError, KeyError):
            pass

    return html_content, one_liner


def send_emails(
    gmail_address: str,
    gmail_password: str,
    subscribers: list[str],
    html_content: str,
    one_liner: str,
):
    """Gmail SMTP로 구독자 전원에게 발송"""
    # GitHub Actions 러너는 UTC이므로 KST 기준 날짜를 명시적으로 사용
    today = datetime.now(tz=KST).strftime("%Y.%m.%d")
    subject = f"🤖 AI Daily Briefing — {today}"

    # SMTP 연결
    print(f"📧 Gmail SMTP 연결 중...")
    server = smtplib.SMTP_SSL("smtp.gmail.com", 465)
    server.login(gmail_address, gmail_password)

    success = 0
    fail = 0

    for email in subscribers:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = f"AI Daily Briefing <{gmail_address}>"
            msg["To"] = email

            # 텍스트 버전 (이메일 클라이언트가 HTML 지원 안 할 때)
            text_part = MIMEText(
                f"AI Daily Briefing — {today}\n\n"
                f"{one_liner}\n\n"
                f"전체 브리핑 보기: https://heogong.github.io/ai-daily-briefing/",
                "plain",
                "utf-8",
            )

            # HTML 버전 (뉴스레터 본문)
            html_part = MIMEText(html_content, "html", "utf-8")

            msg.attach(text_part)
            msg.attach(html_part)

            server.sendmail(gmail_address, email, msg.as_string())
            print(f"  ✅ {email}")
            success += 1

        except Exception as e:
            print(f"  ❌ {email}: {e}")
            fail += 1

    server.quit()
    print(f"\n📊 발송 완료: 성공 {success}명 / 실패 {fail}명")


def main():
    # 환경변수에서 Gmail 정보 가져오기
    gmail_address = os.environ.get("GMAIL_ADDRESS")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")

    if not gmail_address or not gmail_password:
        print("❌ GMAIL_ADDRESS, GMAIL_APP_PASSWORD 환경변수를 설정하세요.")
        return

    # 구독자 로드
    subscribers = get_subscribers()
    if not subscribers:
        print("📭 구독자가 없습니다. subscribers.txt에 이메일을 추가하세요.")
        return

    print(f"👥 구독자 {len(subscribers)}명 발견")

    # 최신 브리핑 로드
    html_content, one_liner = get_latest_briefing()
    print(f"📰 브리핑 로드 완료")

    # 발송
    send_emails(gmail_address, gmail_password, subscribers, html_content, one_liner)


if __name__ == "__main__":
    main()

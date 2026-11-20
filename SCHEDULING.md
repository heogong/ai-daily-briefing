# 스케줄링 (외부 호출 방식)

GitHub Actions의 `schedule` 트리거는 부하 시간대에 지연되거나 실행이 누락되는 경우가 잦아 **사용하지 않습니다.**
대신 외부 스케줄러 **[cron-job.org](https://cron-job.org)** 가 매일 KST 06:00에 GitHub API로 `workflow_dispatch`를 호출합니다.

```
cron-job.org (KST 06:00) ──POST──▶ GitHub API (workflow_dispatch) ──▶ daily-briefing.yml 실행
```

## 원칙

- 워크플로(`.github/workflows/daily-briefing.yml`)에는 `schedule:` 트리거를 **다시 추가하지 않는다.** 외부 호출과 겹치면 브리핑 생성·커밋·**메일 발송이 중복**된다.
- 실행 시각 변경은 워크플로 파일이 아니라 **cron-job.org 작업 설정**에서 한다.
- 워크플로에는 `concurrency: daily-briefing` 그룹이 있어 동시에 두 번 호출돼도 병렬 실행되지 않는다. 단, 첫 실행이 끝난 뒤 다시 호출되면 그대로 한 번 더 실행되므로 중복 호출 자체를 피한다.
- 수동 재실행은 GitHub Actions 탭의 **Run workflow** 버튼을 사용한다.

## 1. GitHub Fine-grained PAT 발급

GitHub → Settings → Developer settings → Personal access tokens → **Fine-grained tokens** → Generate new token

| 항목 | 값 |
|------|----|
| Token name | `cron-job-org-ai-daily` (임의) |
| Expiration | 최대 기간으로 설정 후 **만료일을 캘린더에 기록** |
| Repository access | Only select repositories → `heogong/ai-daily-briefing` |
| Permissions | Repository permissions → **Actions: Read and write** (이것만) |

> 다른 권한은 추가하지 않는다. 토큰이 외부 서비스에 저장되므로 권한을 최소로 유지한다.

## 2. cron-job.org 작업 생성

Create cronjob 에서 아래와 같이 설정한다.

**Common**

| 항목 | 값 |
|------|----|
| Title | AI Daily Briefing |
| URL | `https://api.github.com/repos/heogong/ai-daily-briefing/actions/workflows/daily-briefing.yml/dispatches` |
| Execution schedule | Every day, **06:00** |
| Time zone | **Asia/Seoul** |

**Advanced**

| 항목 | 값 |
|------|----|
| Request method | `POST` |
| Headers | `Authorization: Bearer <PAT>` |
| | `Accept: application/vnd.github+json` |
| | `X-GitHub-Api-Version: 2022-11-28` |
| | `Content-Type: application/json` |
| Request body | `{"ref":"main"}` |
| Treat redirects with HTTP 3xx as success | 해제 |

**Notifications:** "execution of the cronjob fails" 알림을 켠다 (PAT 만료 시 401로 실패하므로 알아챌 수 있도록).

저장 후 **Test run** 으로 응답이 `204 No Content` 인지, GitHub Actions 탭에 `workflow_dispatch` 실행이 생겼는지 확인한다.

## 로컬에서 수동 호출 (테스트용)

```bash
curl -i -X POST \
  -H "Authorization: Bearer $GH_TOKEN" \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  https://api.github.com/repos/heogong/ai-daily-briefing/actions/workflows/daily-briefing.yml/dispatches \
  -d '{"ref":"main"}'
```

## 문제 해결

| 응답 | 원인 |
|------|------|
| `204` | 정상 |
| `401` | PAT 만료/오타 → 재발급 후 cron-job.org 헤더 갱신 |
| `403` | PAT에 Actions 쓰기 권한 없음 또는 대상 저장소 미지정 |
| `404` | URL의 owner/repo/워크플로 파일명 오류, 또는 PAT가 해당 저장소에 접근 불가 |
| `422` | `ref` 브랜치가 없거나 워크플로에 `workflow_dispatch` 트리거가 없음 |

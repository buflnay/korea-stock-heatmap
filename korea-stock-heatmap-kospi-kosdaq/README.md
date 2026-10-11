# 한국 주식 히트맵 — KOSPI / KOSDAQ

TradingView 무료 외부 위젯에서 한국 주식이 표시되지 않는 문제를 피하기 위해 만든 **자체 HTML 히트맵**입니다.

## 기능

- **시장 전환:** `KOSPI` / `KOSDAQ`. 시장별 고정 링크도 지원합니다.
- **시가총액 상위:** `상위 50`, `상위 100`, `상위 200`, `전체`.
  - '전체'는 **GitHub Actions가 네이버 금융 목록의 마지막 페이지까지 정상 수집한 해당 시장의 종목**입니다.
  - 페이지 처리 실패 시 임의의 가짜 종목 목록을 생성하거나 전체인 척하지 않습니다.
- **검색:** 종목명 일부(예: SK)나 6자리 종목코드. **상위 50 버튼을 눌러도 검색은 전체 수집 종목에서** 합니다.
- **네모 크기:** 시가총액 비례. 색상은 **상승 빨강 / 하락 파랑 / 보합 회색**.
- 종목 클릭 → 네이버 금융 종목 상세 이동.
- **무료 호스팅:** Public GitHub 저장소 + GitHub Pages + GitHub Actions.
- PC/모바일 모두 대응. 브라우저는 GitHub Pages의 정적 JSON만 읽으며 **네이버로 로그인하거나 계정 접근 권한을 요청하지 않습니다**.

## 데이터 관련 중요한 사항

- 시세 공급원은 `finance.naver.com/sise/sise_market_sum.naver`의 **공개 시가총액 목록 HTML**이며, 공식 개발자용 API가 아닙니다.
- 업데이트는 **주중 한국시간 10:30, 16:15, 18:15 수집 시도**. 네이버 원본의 시세 지연/휴장/장외거래 등으로 인해 실시간이 아닙니다.
- 네이버 HTML 구조·접속 정책이 바뀌면 수집이 실패할 수 있습니다. **실제 네이버 서버 접근 성공은 이 파일 제작 환경에서 검증하지 못했습니다**. 실제 GitHub Actions 실행 결과를 확인해야 합니다.
- 이용 조건 및 데이터 재게시 권리를 확인하세요. 무제한 배포/상업적 사용을 허용한다는 뜻은 아닙니다.
- 개인 정보, 비밀번호, 주식 계좌, 노션 API 토큰, GitHub PAT는 포함하거나 요구하지 않습니다.

## GitHub 업로드 순서

1. GitHub에서 새 Public 저장소 `korea-stock-heatmap`을 만듭니다. 기존 CNN 저장소와 분리하세요.
2. ZIP의 **내용물**을 압축 해제해 저장소 최상위에 업로드합니다. 반드시 `index.html`이 **저장소 바로 아래**에 있어야 합니다. ZIP 전체나 상위 폴더를 통째로 넣으면 오류가 납니다.
3. 웹 업로드에서 숨김 폴더 `.github`가 빠졌다면, 저장소 **Actions → Skip this and set up a workflow yourself** 또는 **Code → Add file → Create new file**을 열고 파일명을 `.github/workflows/update-heatmap.yml`로 하여 ZIP 속 같은 YAML 코드를 붙여 넣은 뒤 **Commit changes** 하세요.
4. **Settings → Pages → Source = GitHub Actions** 선택. 제안되는 `Static HTML → Configure`는 추가로 누를 필요가 없습니다.
5. **Actions → 한국 주식 히트맵 업데이트 및 배포 → Run workflow**를 실행합니다. 초록색 체크가 나와야 합니다. 빨간 X가 뜨면 작업 로그에서 네이버 HTML 가져오기/파싱 오류를 확인해 주세요.
6. `https://<GitHub 사용자명>.github.io/korea-stock-heatmap/` 접속 후 실제 기업과 데이터 갱신 날짜가 보이는지 확인하세요. 최초에는 JSON이 비어 있으므로 첫 수집 성공 전에는 빈 상태가 표시됩니다.
7. 노션에서 `/임베드`를 선택해 아래 시장별 링크를 각각 넣거나, 하나의 임베드에서 KOSPI/KOSDAQ 버튼으로 전환할 수 있습니다.

### 노션 삽입 URL

- 코스피: `https://<GitHub 사용자명>.github.io/korea-stock-heatmap/?market=KOSPI&limit=200`
- 코스닥: `https://<GitHub 사용자명>.github.io/korea-stock-heatmap/?market=KOSDAQ&limit=200`
- 처음부터 전체 보기: 위 URL의 `limit=200`을 `limit=all`로 바꾸세요.
- 미리보기: 위 URL의 뒤에 `&demo=1`을 붙입니다. **디자인 전용 가짜 시연 숫자**이며 실제 투자 지표가 아닙니다. 노션 실사용 URL에는 사용하지 마세요.

## 업데이트 방식 및 주의

GitHub Actions가 Python 표준 라이브러리만 사용하여 네이버 공개 페이지를 순차적으로 읽은 후 `data/kospi.json`과 `data/kosdaq.json`을 만들어 GitHub Pages에 배포합니다. 수집 실패 시 데이터 파일을 빈 배열로 덮어쓰지 않으며, 자동 배포는 실패로 표시됩니다.

이 프로젝트는 브라우저에서 민감한 쿠키/토큰을 수집하지 않습니다. 다만 **Public 저장소 코드와 Pages 페이지는 누구나 볼 수 있습니다**. 기존 Private 저장소는 변경되지 않습니다.

# NAVER 검색어 종합 EDA 대시보드

쉼표로 구분한 최대 5개의 검색어를 대상으로 네이버 검색 결과, 검색어 트렌드, 쇼핑 인사이트를 비교하는 개인용 Streamlit 대시보드입니다.

## 제공 범위

- 검색 API: 뉴스, 블로그, 카페글, 장소, 웹문서, 이미지 결과 수집 및 통합 분석
- 검색어 트렌드: 일·주·월 단위 통합검색 상대지수와 상관관계·히트맵 분석
- 쇼핑 인사이트: 사용자가 선택한 쇼핑 분야별 검색 클릭 상대지수
- 검색 결과 구성, 연관 단어 빈도, 채널별 최신성, 주요 출처 분석과 CSV 다운로드
- 검색어 비교와 동의어 그룹 비교

> 검색어 트렌드와 쇼핑 인사이트는 모두 상대지수입니다. 같은 API 안에서 추이를 비교할 수는 있지만, 두 API의 숫자를 절대 검색량처럼 비교하거나 합산하면 안 됩니다.

## API 발급과 설정

1. [NAVER API HUB 애플리케이션 관리](https://console.ncloud.com/naver-api-hub/application)에 접속합니다.
2. **애플리케이션 등록**에서 검색, 검색어 트렌드, 쇼핑 인사이트 API를 선택합니다.
3. 등록한 애플리케이션의 **인증 정보**에서 Client ID와 Client Secret을 확인합니다.
4. `.env.example`을 복사해 `.env` 파일을 만들고 값을 입력합니다.

```bash
cp .env.example .env
```

```dotenv
NAVER_API_CLIENT_ID=발급받은_ID
NAVER_API_CLIENT_SECRET=발급받은_Secret
```

`.env`는 `.gitignore`에 포함되어 있어 Git에 올리지 않습니다. 대시보드는 화면에서 ID나 Secret을 입력받거나 저장하지 않으며, `.env` 값이 없으면 API 호출을 막고 발급 안내를 표시합니다.

## Streamlit Community Cloud 시크릿 설정

GitHub에는 API 키를 올리지 마세요. Community Cloud에서 앱을 배포한 뒤 **앱 설정 → Secrets**에 아래 내용을 붙여 넣고 저장합니다. 값에는 NAVER API HUB에서 발급한 실제 인증 정보를 넣습니다.

```toml
NAVER_API_CLIENT_ID = "발급받은_CLIENT_ID"
NAVER_API_CLIENT_SECRET = "발급받은_CLIENT_SECRET"
```

동일한 템플릿은 `streamlit_secrets.toml.example`에도 있습니다. 앱은 Community Cloud의 시크릿을 먼저 읽고, 로컬 실행 때만 `.env` 값을 사용합니다.

시크릿을 등록하지 않아도 앱 왼쪽 사이드바의 **API Key 인증 관리**에서 Client ID와 Client Secret을 직접 입력해 실행할 수 있습니다. 직접 입력한 값은 현재 세션에서만 사용되며 파일이나 GitHub에 저장되지 않습니다. 공개 앱에서는 각 사용자가 자신의 API 키를 입력하게 할 때 적합하며, 운영자 키를 공통으로 쓰려면 Community Cloud 시크릿 등록을 권장합니다.

## 실행

```bash
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt
streamlit run app.py
```

이미 `.venv`가 있으면 새로 만들지 말고 해당 환경을 사용하세요.

## 입력 방법

기본 모드에서는 쉼표가 독립 검색어를 구분합니다.

```text
커피, 차, 노트북
```

**동의어 그룹 모드**에서는 `|`로 같은 주제어의 동의어를 묶습니다.

```text
커피|카페인, 차|티
```

입력값은 공백·빈값·중복을 제거하며, 최대 5개만 분석합니다. 제외된 항목은 화면에서 알립니다.

## 데이터 수집 방식

| 데이터 | 방식 | API 경로 | 주요 값 |
| --- | --- | --- | --- |
| 뉴스·블로그·카페글·장소·웹문서·이미지 | GET | `/search/v1/{유형}` | `total`, `items` |
| 검색어 트렌드 | POST | `/search-trend/v1/search` | 월별 `ratio` |
| 쇼핑 분야 추이 | POST | `/shopping/v1/categories` | 월별 `ratio` |

모든 요청은 `https://naverapihub.apigw.ntruss.com`을 사용하며, `X-NCP-APIGW-API-KEY-ID`, `X-NCP-APIGW-API-KEY` 헤더로 인증합니다. POST 요청에는 `Content-Type: application/json`을 넣습니다.

## 쇼핑 인사이트 방식

쇼핑 인사이트의 키워드별 API는 쇼핑 분야 코드를 필수로 요구합니다. 따라서 서로 다른 상품군의 임의 검색어를 자동으로 분류해 비교하지 않습니다. 대신 대시보드 왼쪽에서 최대 3개의 쇼핑 분야를 고르면, 분야별 검색 클릭 추이를 표시합니다. 검색어 자체의 비교는 카테고리 제약이 없는 **통합검색 관심도 추이**에서 확인합니다.

## EDA 해석 기준

- 검색 결과 수: 해당 검색 유형에서 API가 반환한 결과 수입니다. 전체 웹 관심도의 절대 척도가 아닙니다.
- 검색어 트렌드: 네이버 통합검색 내 주제어의 기간별 상대 검색 추이입니다.
- 쇼핑 인사이트: 사용자가 선택한 쇼핑 분야 안에서의 검색 클릭 상대 추이입니다.
- 검색 결과 수, 검색어 트렌드, 쇼핑 클릭 지수를 합산해 하나의 점수로 만들지 않습니다.

## 제한과 오류 처리

- 검색 API의 일일 호출 한도는 25,000회입니다.
- 앱은 실행 중 메모리 캐시를 사용해 같은 요청의 반복 호출을 줄입니다. 앱을 재시작하면 새로 조회합니다.
- 401은 인증 정보 또는 API 권한을, 429는 호출 한도를 확인해야 합니다.
- 검색 결과가 없거나 쇼핑 카테고리가 맞지 않으면 빈 결과가 나타날 수 있습니다.

## 참고 문서

- [NAVER API HUB 개요](https://api.ncloud-docs.com/docs/naver-api-hub-overview)
- [검색어 트렌드 조회](https://api.ncloud-docs.com/docs/naver-api-hub-search-trend)
- [기기별 쇼핑 인사이트 조회](https://api.ncloud-docs.com/docs/naver-api-hub-shopping-insight-device)

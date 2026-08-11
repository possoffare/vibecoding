"""NAVER API HUB 기반 종합 검색어 EDA 대시보드."""

import os
import re
from collections import Counter
from datetime import date, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests
import streamlit as st
from dotenv import load_dotenv


BASE_URL = "https://naverapihub.apigw.ntruss.com"
APP_DIR = Path(__file__).resolve().parent
SEARCH_TYPES = {
    "뉴스": "news",
    "블로그": "blog",
    "카페글": "cafearticle",
    "장소": "local",
    "웹문서": "webkr",
    "이미지": "image",
}
SHOPPING_CATEGORIES = {
    "패션의류": "50000000", "패션잡화": "50000001", "화장품/미용": "50000002",
    "디지털/가전": "50000003", "가구/인테리어": "50000004", "출산/육아": "50000005",
    "식품": "50000006", "스포츠/레저": "50000007", "생활/건강": "50000008",
    "여가/생활편의": "50000009", "면세점": "50000010",
}
STOPWORDS = {"그리고", "하지만", "오늘", "이번", "정리", "추천", "사용", "후기", "정보", "관련", "대한", "있는", "에서", "으로", "하는", "합니다", "합니다"}


def load_credentials() -> tuple[str, str]:
    """배포 시 시크릿과 로컬 .env에 저장된 인증 정보를 읽는다."""
    load_dotenv(APP_DIR / ".env")
    client_id = st.secrets.get("NAVER_API_CLIENT_ID", os.getenv("NAVER_API_CLIENT_ID", ""))
    client_secret = st.secrets.get("NAVER_API_CLIENT_SECRET", os.getenv("NAVER_API_CLIENT_SECRET", ""))
    return str(client_id).strip(), str(client_secret).strip()


def resolve_credentials(saved_id: str, saved_secret: str, entered_id: str, entered_secret: str) -> tuple[str, str, str]:
    """직접 입력한 키를 우선 사용하고, 둘 중 하나만 입력한 경우 실행을 막는다."""
    if entered_id or entered_secret:
        if not entered_id or not entered_secret:
            return "", "", "incomplete"
        return entered_id.strip(), entered_secret.strip(), "entered"
    if saved_id and saved_secret:
        return saved_id, saved_secret, "saved"
    return "", "", "missing"


def api_headers(client_id: str, client_secret: str, json_body: bool = False) -> dict[str, str]:
    headers = {"X-NCP-APIGW-API-KEY-ID": client_id, "X-NCP-APIGW-API-KEY": client_secret}
    if json_body:
        headers["Content-Type"] = "application/json"
    return headers


def request_api(method: str, path: str, client_id: str, client_secret: str, *, params: dict[str, Any] | None = None, body: dict[str, Any] | None = None) -> dict[str, Any]:
    """API 오류를 대시보드에서 읽기 쉬운 오류로 변환한다."""
    try:
        response = requests.request(method, f"{BASE_URL}{path}", headers=api_headers(client_id, client_secret, body is not None), params=params, json=body, timeout=20)
    except requests.RequestException as error:
        raise RuntimeError(f"네트워크 오류: {error}") from error
    if response.ok:
        return response.json()
    try:
        detail = response.json()
    except ValueError:
        detail = response.text
    if response.status_code == 401:
        raise RuntimeError("인증에 실패했습니다. .env의 API ID·Secret과 API 권한을 확인하세요.")
    if response.status_code == 429:
        raise RuntimeError("API 호출 한도를 초과했습니다. 잠시 후 다시 시도하세요.")
    raise RuntimeError(f"API 호출 실패 ({response.status_code}): {detail}")


def parse_keywords(raw: str, group_mode: bool) -> tuple[list[dict[str, Any]], list[str]]:
    """쉼표 입력을 정리하고 최대 다섯 개 주제어만 남긴다."""
    groups, excluded, seen = [], [], set()
    for token in raw.split(","):
        clean = token.strip()
        if not clean:
            continue
        words = [part.strip() for part in clean.split("|") if part.strip()] if group_mode else [clean]
        identifier = tuple(word.lower() for word in words)
        if not words or identifier in seen:
            excluded.append(clean)
            continue
        seen.add(identifier)
        groups.append({"name": " · ".join(words), "keywords": words})
    if len(groups) > 5:
        excluded.extend(group["name"] for group in groups[5:])
        groups = groups[:5]
    return groups, excluded


def strip_html(value: str) -> str:
    return re.sub(r"<[^>]+>", "", value or "").strip()


def parse_item_date(value: str) -> Any:
    if not value:
        return pd.NaT
    for fmt in ("%Y%m%d", "%Y-%m-%d"):
        parsed = pd.to_datetime(value, format=fmt, errors="coerce")
        if not pd.isna(parsed):
            return parsed
    return pd.to_datetime(value, errors="coerce", utc=True).tz_localize(None) if not pd.isna(pd.to_datetime(value, errors="coerce", utc=True)) else pd.NaT


@st.cache_data(ttl=3600, show_spinner=False)
def collect_search(query: str, search_type: str, display: int, client_id: str, client_secret: str) -> dict[str, Any]:
    return request_api("GET", f"/search/v1/{search_type}", client_id, client_secret, params={"query": query, "display": display})


@st.cache_data(ttl=3600, show_spinner=False)
def collect_search_trend(groups: tuple[tuple[str, tuple[str, ...]], ...], start: str, end: str, unit: str, client_id: str, client_secret: str) -> dict[str, Any]:
    body = {"startDate": start, "endDate": end, "timeUnit": unit, "keywordGroups": [{"groupName": name, "keywords": list(words)} for name, words in groups]}
    return request_api("POST", "/search-trend/v1/search", client_id, client_secret, body=body)


@st.cache_data(ttl=3600, show_spinner=False)
def collect_shopping_category_trends(categories: tuple[str, ...], start: str, end: str, unit: str, client_id: str, client_secret: str) -> dict[str, Any]:
    body = {"startDate": start, "endDate": end, "timeUnit": unit, "category": [{"name": name, "param": [SHOPPING_CATEGORIES[name]]} for name in categories]}
    return request_api("POST", "/shopping/v1/categories", client_id, client_secret, body=body)


def trend_frame(payload: dict[str, Any], source: str) -> pd.DataFrame:
    rows = []
    for result in payload.get("results", []):
        name = result.get("title") or result.get("name") or "미상"
        for point in result.get("data", []):
            rows.append({"기간": point["period"], "항목": name, "상대지수": point["ratio"], "출처": source})
    return pd.DataFrame(rows)


def normalize_item(keyword: str, kind: str, item: dict[str, Any]) -> dict[str, Any]:
    """서로 다른 검색 API 응답을 하나의 분석용 테이블로 맞춘다."""
    title = strip_html(item.get("title", ""))
    description = strip_html(item.get("description", item.get("category", "")))
    link = item.get("link", item.get("originallink", ""))
    if kind == "뉴스":
        author, raw_date = urlparse(item.get("originallink", "")).netloc, item.get("pubDate", "")
    elif kind == "블로그":
        author, raw_date = item.get("bloggername", ""), item.get("postdate", "")
    elif kind == "카페글":
        author, raw_date = item.get("cafename", ""), item.get("postdate", "")
    elif kind == "장소":
        author, raw_date = item.get("category", ""), ""
        description = " · ".join(part for part in [item.get("category", ""), item.get("roadAddress", "") or item.get("address", "")] if part)
    else:
        author, raw_date = urlparse(link).netloc, ""
    return {"검색어": keyword, "유형": kind, "제목": title or "제목 없음", "설명": description, "출처/작성자": author or "미상", "발행일": parse_item_date(raw_date), "링크": link, "썸네일": item.get("thumbnail", "")}


def collect_results(groups: list[dict[str, Any]], display: int, client_id: str, client_secret: str) -> tuple[pd.DataFrame, list[str]]:
    rows, errors = [], []
    for group in groups:
        query = group["keywords"][0]
        for label, endpoint in SEARCH_TYPES.items():
            try:
                payload = collect_search(query, endpoint, display, client_id, client_secret)
                rows.extend(normalize_item(group["name"], label, item) for item in payload.get("items", []))
            except RuntimeError as error:
                errors.append(f"{group['name']} · {label}: {error}")
    return pd.DataFrame(rows), errors


def trend_summary(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame()
    rows = []
    for name, group in frame.groupby("항목"):
        peak = group.loc[group["상대지수"].idxmax()]
        latest = group.sort_values("기간").iloc[-1]
        rows.append({"검색어": name, "평균 지수": round(group["상대지수"].mean(), 2), "최고 지수": round(peak["상대지수"], 2), "최고 시점": peak["기간"], "최근 지수": round(latest["상대지수"], 2), "변동성(표준편차)": round(group["상대지수"].std(ddof=0), 2)})
    return pd.DataFrame(rows).sort_values("최근 지수", ascending=False)


def keyword_frequency(results: pd.DataFrame, groups: list[dict[str, Any]]) -> pd.DataFrame:
    excluded = {word.lower() for group in groups for word in group["keywords"]} | STOPWORDS
    text = " ".join((results["제목"].fillna("") + " " + results["설명"].fillna("")).tolist())
    words = [word for word in re.findall(r"[가-힣A-Za-z]{2,}", text) if word.lower() not in excluded]
    return pd.DataFrame(Counter(words).most_common(20), columns=["연관 단어", "언급 수"])


def base_figure(figure: go.Figure) -> go.Figure:
    figure.update_layout(
        template="plotly_white",
        paper_bgcolor="#fff8e9",
        plot_bgcolor="#fff8e9",
        font={"family": "Pretendard, Apple SD Gothic Neo, sans-serif", "color": "#101038"},
        colorway=["#101038", "#f16d52", "#168a78", "#d7ee5c", "#6f54b8"],
        margin={"l": 20, "r": 20, "t": 56, "b": 20},
        legend_title_text="",
    )
    figure.update_xaxes(gridcolor="#eacbaa", linecolor="#101038", zerolinecolor="#eacbaa")
    figure.update_yaxes(gridcolor="#eacbaa", linecolor="#101038", zerolinecolor="#eacbaa")
    return figure


def render_overview(search_trend: pd.DataFrame, summary: pd.DataFrame, results: pd.DataFrame) -> None:
    st.subheader("검색 관심도 핵심 지표")
    cards = st.columns(max(1, len(summary)))
    for column, (_, row) in zip(cards, summary.iterrows()):
        column.metric(row["검색어"], f"{row['최근 지수']:.1f}", f"평균 {row['평균 지수']:.1f}")

    chart_col, table_col = st.columns([3, 2])
    with chart_col:
        figure = px.line(search_trend, x="기간", y="상대지수", color="항목", markers=True, title="통합검색 상대 관심도 추이")
        st.plotly_chart(base_figure(figure), use_container_width=True)
    with table_col:
        st.markdown("#### 표 1. 검색어 추이 요약")
        st.dataframe(summary, hide_index=True, use_container_width=True)

    left, right = st.columns(2)
    with left:
        pivot = search_trend.pivot(index="기간", columns="항목", values="상대지수")
        correlation = pivot.corr().round(2)
        figure = px.imshow(correlation, text_auto=".2f", color_continuous_scale="RdBu", zmin=-1, zmax=1, title="검색 패턴 상관관계")
        st.plotly_chart(base_figure(figure), use_container_width=True)
        st.markdown("#### 표 2. 최근 시점 상대지수")
        st.dataframe(search_trend.sort_values("기간").groupby("항목", as_index=False).tail(1)[["항목", "기간", "상대지수"]], hide_index=True, use_container_width=True)
    with right:
        heat = search_trend.pivot(index="항목", columns="기간", values="상대지수")
        figure = px.imshow(heat, aspect="auto", color_continuous_scale="Teal", title="검색어·기간별 관심도 히트맵")
        st.plotly_chart(base_figure(figure), use_container_width=True)
        st.markdown("#### 표 3. 검색 결과 수집 현황")
        coverage = results.pivot_table(index="검색어", columns="유형", values="제목", aggfunc="count", fill_value=0).reset_index()
        st.dataframe(coverage, hide_index=True, use_container_width=True)

    if not results.empty:
        counts = results.groupby(["검색어", "유형"]).size().reset_index(name="결과 수")
        figure = px.bar(counts, x="검색어", y="결과 수", color="유형", barmode="stack", title="검색어별 채널 결과 구성")
        st.plotly_chart(base_figure(figure), use_container_width=True)


def render_content_eda(results: pd.DataFrame, groups: list[dict[str, Any]]) -> None:
    st.subheader("뉴스 · 블로그 · 카페 · 장소 콘텐츠 EDA")
    if results.empty:
        st.info("표시할 검색 결과가 없습니다.")
        return
    terms = keyword_frequency(results, groups)
    left, right = st.columns(2)
    with left:
        figure = px.bar(terms.head(15), x="언급 수", y="연관 단어", orientation="h", title="상위 연관 단어 빈도", color="언급 수", color_continuous_scale="Teal")
        st.plotly_chart(base_figure(figure), use_container_width=True)
    with right:
        sources = results[results["출처/작성자"] != "미상"].groupby("출처/작성자").size().reset_index(name="문서 수").nlargest(15, "문서 수")
        figure = px.bar(sources.sort_values("문서 수"), x="문서 수", y="출처/작성자", orientation="h", title="주요 출처·작성자")
        st.plotly_chart(base_figure(figure), use_container_width=True)

    dated = results.dropna(subset=["발행일"]).copy()
    if not dated.empty:
        dated["월"] = dated["발행일"].dt.strftime("%Y-%m")
        freshness = dated.groupby(["월", "유형"]).size().reset_index(name="문서 수")
        figure = px.area(freshness, x="월", y="문서 수", color="유형", title="채널별 최신 콘텐츠 분포")
        st.plotly_chart(base_figure(figure), use_container_width=True)

    a, b, c = st.columns(3)
    with a:
        st.markdown("#### 표 4. 연관 단어 빈도")
        st.dataframe(terms.head(15), hide_index=True, use_container_width=True)
    with b:
        st.markdown("#### 표 5. 유형별 결과 수")
        st.dataframe(results.groupby("유형").size().reset_index(name="결과 수").sort_values("결과 수", ascending=False), hide_index=True, use_container_width=True)
    with c:
        st.markdown("#### 표 6. 검색어별 출처 수")
        st.dataframe(results.groupby("검색어", as_index=False)["출처/작성자"].nunique().rename(columns={"출처/작성자": "고유 출처 수"}), hide_index=True, use_container_width=True)

    st.markdown("#### 표 7. 통합 검색 결과")
    detail = results[["검색어", "유형", "제목", "설명", "출처/작성자", "발행일", "링크"]].copy()
    detail["발행일"] = detail["발행일"].dt.strftime("%Y-%m-%d")
    st.dataframe(detail, hide_index=True, use_container_width=True, column_config={"링크": st.column_config.LinkColumn("링크", display_text="열기")})


def render_shopping(shopping: pd.DataFrame) -> None:
    st.subheader("쇼핑 분야 인사이트")
    st.caption("입력 검색어와 독립된 쇼핑 분야별 검색 클릭 상대지수입니다.")
    if shopping.empty:
        st.info("선택한 쇼핑 분야의 데이터가 없습니다.")
        return
    left, right = st.columns([3, 2])
    with left:
        figure = px.line(shopping, x="기간", y="상대지수", color="항목", markers=True, title="쇼핑 분야별 검색 클릭 추이")
        st.plotly_chart(base_figure(figure), use_container_width=True)
    with right:
        summary = trend_summary(shopping)
        st.markdown("#### 표 8. 쇼핑 분야 요약")
        st.dataframe(summary, hide_index=True, use_container_width=True)

    latest = shopping.sort_values("기간").groupby("항목", as_index=False).tail(1)
    figure = px.bar(latest, x="항목", y="상대지수", color="항목", title="최근 시점 쇼핑 분야 상대지수")
    st.plotly_chart(base_figure(figure), use_container_width=True)


def apply_style() -> None:
    st.markdown("""<style>
    :root {
        --ink: #101038;
        --muted: #484567;
        --paper: #fff8e9;
        --cream: #fff1dc;
        --coral: #f16d52;
        --lime: #dfff62;
        --line: #101038;
    }
    .stApp {
        color: var(--ink);
        background: var(--coral);
    }
    [data-testid="stHeader"] { background: rgba(255, 248, 233, 0.94); }
    [data-testid="stSidebar"] {
        background: var(--ink);
        border-right: 0;
    }
    [data-testid="stSidebar"] > div:first-child { padding-top: 1.2rem; }
    [data-testid="stSidebar"] * { color: var(--paper); }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { color: #d8d2f2; }
    .block-container { max-width: 1450px; padding: 2.2rem 2.4rem 3.4rem; }
    h1 {
        color: var(--ink) !important;
        -webkit-text-fill-color: var(--ink);
        font-size: clamp(2.3rem, 5vw, 4.2rem);
        font-weight: 900;
        letter-spacing: -0.07em;
        line-height: 1.05;
        margin-bottom: 0.75rem;
    }
    h2, h3 { color: var(--ink); letter-spacing: -0.045em; font-weight: 850; }
    [data-testid="stCaptionContainer"] { color: var(--muted); }
    [data-testid="stMetric"] {
        background: var(--paper);
        border: 2px solid var(--ink);
        border-radius: 3px;
        box-shadow: 7px 7px 0 var(--ink);
        padding: 18px;
    }
    [data-testid="stMetric"]:hover { transform: translate(-2px, -2px); box-shadow: 10px 10px 0 var(--lime); }
    [data-testid="stMetricValue"] { color: var(--coral); font-weight: 900; }
    [data-testid="stTextInput"] input,
    [data-testid="stTextArea"] textarea,
    [data-baseweb="select"] > div {
        background: #fff7e8 !important;
        border: 1.5px solid var(--ink) !important;
        border-radius: 2px !important;
        color: var(--ink) !important;
    }
    [data-testid="stTextInput"] input:focus,
    [data-testid="stTextArea"] textarea:focus {
        border-color: var(--lime) !important;
        box-shadow: 3px 3px 0 var(--lime) !important;
    }
    .stButton > button, [data-testid="stLinkButton"] a {
        background: var(--ink) !important;
        border: 2px solid var(--ink) !important;
        border-radius: 2px !important;
        color: #fff7e8 !important;
        font-weight: 900 !important;
        box-shadow: 4px 4px 0 var(--lime);
        transition: transform 160ms ease, filter 160ms ease;
    }
    .stButton > button:hover, [data-testid="stLinkButton"] a:hover {
        filter: none;
        transform: translate(2px, 2px);
        box-shadow: 1px 1px 0 var(--lime);
    }
    .stTabs [data-baseweb="tab-list"] { gap: 0; border-bottom: 2px solid var(--ink); padding: 0; background: transparent; border-radius: 0; }
    .stTabs [data-baseweb="tab"] { border-radius: 0; color: var(--ink); font-size: 0.96rem; font-weight: 800; padding: 10px 13px; }
    .stTabs [aria-selected="true"] { background: var(--ink); color: #fff7e8; }
    [data-testid="stAlert"] { background: var(--cream); border: 2px solid var(--ink); border-radius: 2px; color: var(--ink); }
    [data-testid="stExpander"] { background: #fff7e8; border: 2px solid var(--ink); border-radius: 2px; }
    [data-testid="stDataFrame"] { border: 2px solid var(--ink); border-radius: 2px; overflow: hidden; }
    </style>""", unsafe_allow_html=True)


def main() -> None:
    st.set_page_config(page_title="NAVER 키워드 종합 EDA", page_icon="🔎", layout="wide")
    apply_style()
    st.title("🔎 NAVER 키워드 종합 EDA 대시보드")
    st.caption("통합검색 트렌드, 뉴스·블로그·카페·장소 콘텐츠, 쇼핑 분야를 한 화면에서 탐색합니다.")

    today = date.today()
    saved_id, saved_secret = load_credentials()
    with st.sidebar:
        st.header("🔑 API Key 인증 관리")
        entered_id, entered_secret = "", ""
        if saved_id and saved_secret:
            st.success("Streamlit 시크릿으로 인증됨")
            st.caption("배포 설정에 저장된 API 키를 사용합니다.")
            with st.expander("다른 API 키 직접 입력", expanded=False):
                entered_id = st.text_input("Client ID", type="password", placeholder="Client ID를 입력하세요")
                entered_secret = st.text_input("Client Secret", type="password", placeholder="Client Secret을 입력하세요")
                st.caption("입력값은 현재 세션에서만 사용되며 파일이나 GitHub에 저장되지 않습니다.")
        else:
            st.caption("NAVER API HUB의 Client ID와 Client Secret을 직접 입력할 수 있습니다.")
            entered_id = st.text_input("Client ID", type="password", placeholder="Client ID를 입력하세요")
            entered_secret = st.text_input("Client Secret", type="password", placeholder="Client Secret을 입력하세요")
            st.caption("입력값은 현재 세션에서만 사용되며 파일이나 GitHub에 저장되지 않습니다.")
        st.link_button("NAVER API HUB에서 키 발급하기", "https://console.ncloud.com/naver-api-hub/application", use_container_width=True)
        st.divider()
        st.header("분석 설정")
        raw = st.text_area("검색어", value="돈까스, 파스타, 필터커피", help="쉼표로 구분해 최대 5개를 입력하세요.")
        group_mode = st.toggle("동의어 그룹 모드", help="`커피|카페인, 차|티`처럼 `|`로 동의어를 묶습니다.")
        start = st.date_input("시작일", value=today - timedelta(days=365), max_value=today)
        end = st.date_input("종료일", value=today, min_value=start, max_value=today)
        unit_label = st.selectbox("시간 단위", ["월간", "주간", "일간"], index=0)
        unit = {"월간": "month", "주간": "week", "일간": "date"}[unit_label]
        display = st.slider("채널별 수집 결과", min_value=5, max_value=100, value=20, step=5)
        shopping_categories = st.multiselect("쇼핑 분야 비교", list(SHOPPING_CATEGORIES), default=[], max_selections=3)
        run = st.button("🚀 종합 EDA 분석 실행", type="primary", use_container_width=True)
        st.divider()
        st.markdown("#### 데이터 해석")
        st.caption("검색어 트렌드와 쇼핑 인사이트는 각각 API 내부에서만 비교 가능한 상대지수입니다. 두 수치를 절대 비교하거나 합산하지 마세요.")

    client_id, client_secret, credential_source = resolve_credentials(saved_id, saved_secret, entered_id, entered_secret)
    if credential_source == "incomplete":
        st.warning("사이드바의 Client ID와 Client Secret을 모두 입력해 주세요.")
        return
    if credential_source == "missing":
        st.error("사이드바에 NAVER API Client ID와 Client Secret을 입력한 뒤 분석을 실행하세요.")
        return
    if credential_source == "entered":
        st.info("사이드바에 직접 입력한 API 키를 사용합니다. 입력값은 현재 세션이 끝나면 사라집니다.")

    if not run:
        st.info("왼쪽에서 검색어와 기간을 설정한 뒤 **종합 EDA 분석 실행**을 누르세요.")
        return
    groups, excluded = parse_keywords(raw, group_mode)
    if not groups:
        st.warning("분석할 검색어를 하나 이상 입력하세요.")
        return
    if excluded:
        st.warning("제외된 항목: " + ", ".join(excluded))

    group_tuple = tuple((group["name"], tuple(group["keywords"])) for group in groups)
    with st.spinner("검색어 트렌드와 채널 데이터를 수집하는 중입니다..."):
        try:
            search_trend = trend_frame(collect_search_trend(group_tuple, start.isoformat(), end.isoformat(), unit, client_id, client_secret), "검색어 트렌드")
            results, errors = collect_results(groups, display, client_id, client_secret)
        except RuntimeError as error:
            st.error(str(error))
            return
    if errors:
        with st.expander(f"일부 채널 수집 오류 {len(errors)}건"):
            st.warning("\n\n".join(errors))
    shopping = pd.DataFrame()
    if shopping_categories:
        try:
            shopping = trend_frame(collect_shopping_category_trends(tuple(shopping_categories), start.isoformat(), end.isoformat(), unit, client_id, client_secret), "쇼핑 인사이트")
        except RuntimeError as error:
            st.warning(f"쇼핑 인사이트: {error}")

    summary = trend_summary(search_trend)
    overview_tab, content_tab, shopping_tab, data_tab = st.tabs(["📈 검색어 트렌드", "📰 뉴스·블로그·카페·장소 EDA", "🛒 쇼핑 분야", "💾 원본 데이터"])
    with overview_tab:
        render_overview(search_trend, summary, results)
    with content_tab:
        render_content_eda(results, groups)
    with shopping_tab:
        render_shopping(shopping)
    with data_tab:
        st.markdown("#### 표 9. 검색어 트렌드 원본")
        st.dataframe(search_trend, hide_index=True, use_container_width=True)
        st.download_button("검색어 트렌드 CSV 다운로드", search_trend.to_csv(index=False).encode("utf-8-sig"), "search_trend.csv", "text/csv")
        st.markdown("#### 표 10. 검색 결과 원본")
        st.dataframe(results, hide_index=True, use_container_width=True)
        st.download_button("검색 결과 CSV 다운로드", results.to_csv(index=False).encode("utf-8-sig"), "search_results.csv", "text/csv")


if __name__ == "__main__":
    main()

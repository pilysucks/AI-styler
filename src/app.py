from __future__ import annotations

from pathlib import Path
from typing import Dict, List

import pandas as pd
import streamlit as st

from services import deepseek
from services import inventory
from services import recommendations


PROJECT_ROOT = Path(__file__).resolve().parents[1]


st.set_page_config(page_title="AI Styler", layout="wide", page_icon="🧥")


def _init_state() -> None:
    if "inventory_df" not in st.session_state:
        st.session_state.inventory_df = inventory.load_inventory()
    if "profile" not in st.session_state:
        st.session_state.profile = {
            "gender": "여성",
            "style_preferences": [],
            "season": [],
            "budget": 20,
        }
    if "catalog_options" not in st.session_state:
        st.session_state.catalog_options = {
            "limit_total": 120,
            "include_static": True,
            "include_musinsa": True,
            "include_kream": True,
            "per_category_cap": None,
            "refresh_static": True,
        }
    if "integrations" not in st.session_state:
        st.session_state.integrations = {
            "musinsa_cookie": "",
            "kream_cookie": "",
        }


def _refresh_inventory() -> None:
    st.session_state.inventory_df = inventory.load_inventory()


def _update_profile(gender: str, styles: List[str], seasons: List[str], budget: int) -> None:
    st.session_state.profile.update(
        {
            "gender": gender,
            "style_preferences": styles,
            "season": seasons,
            "budget": budget,
        }
    )


def _display_inventory_table(df: pd.DataFrame) -> None:
    summary = inventory.inventory_summary(df)
    st.metric("보유 총 아이템", summary.get("total", 0))
    if summary.get("by_category"):
        st.caption("카테고리 분포")
        st.json(summary["by_category"])
    st.dataframe(inventory.to_display_frame(df), use_container_width=True, hide_index=True)


def _resolve_image_path(image_path: str | None) -> str | None:
    if not image_path:
        return None
    candidate = PROJECT_ROOT / image_path
    return str(candidate) if candidate.exists() else None


def _render_outfit_card(outfit: Dict) -> None:
    with st.container(border=True):
        st.subheader(outfit["title"], divider="gray")
        st.write(outfit["description"])
        st.caption(f"스타일 태그: {', '.join(outfit['style_tags']) if outfit['style_tags'] else '무드 탐색 중'}")
        cols = st.columns(len(outfit["items"]))
        for col, item in zip(cols, outfit["items"]):
            with col:
                st.markdown(f"**{item.get('category', '아이템')}**")
                image_path = _resolve_image_path(item.get("image_path"))
                if image_path:
                    st.image(image_path, use_column_width=True)
                st.caption(item.get("name", "이름 없음"))
                meta = []
                if item.get("color"):
                    meta.append(item["color"])
                if item.get("season"):
                    meta.append("/".join(item["season"]))
                if meta:
                    st.write(" · ".join(meta))


def _render_product_card(item: Dict) -> None:
    if item.get("image_url"):
        st.image(item["image_url"], use_column_width=True)

    st.markdown(f"**{item['name']}**")

    price = item.get("price_krw")
    if price:
        st.write(f"{price:,.0f}원")

    meta_parts = []
    if item.get("source"):
        meta_parts.append(item["source"])
    if item.get("score") is not None:
        meta_parts.append(f"점수 {item['score']:.2f}")
    if meta_parts:
        st.caption(" · ".join(meta_parts))

    if item.get("reason"):
        st.caption(item["reason"])

    caption = None
    if deepseek.is_configured():
        caption = deepseek.product_caption(
            name=item.get("name", ""),
            price_krw=item.get("price_krw"),
            style_tags=item.get("style_tags", []),
            source=item.get("source"),
        )
    if caption:
        st.write(caption)

    if item.get("style_tags"):
        st.caption(f"스타일: {', '.join(item['style_tags'])}")

    st.link_button("구매하러 가기", item["product_url"], type="primary")

    outfit_examples = item.get("outfit_example") or []
    if outfit_examples:
        with st.expander("내 옷장과 매치하기"):
            for idx, outfit in enumerate(outfit_examples, start=1):
                st.markdown(f"**코디 아이디어 #{idx}**")
                for piece in outfit:
                    if isinstance(piece, dict) and piece.get("name"):
                        line = piece.get("category") or "아이템"
                        line += f" | {piece['name']}"
                        if piece.get("color"):
                            line += f" ({piece['color']})"
                        st.write(line)


def _render_product_grid(items: List[Dict]) -> None:
    if not items:
        st.warning("추천 아이템을 찾지 못했어요")
        return

    columns = 3
    for start in range(0, len(items), columns):
        row_items = items[start : start + columns]
        cols = st.columns(len(row_items))
        for col, item in zip(cols, row_items):
            with col:
                _render_product_card(item)


def main() -> None:
    _init_state()

    st.title("AI Styler")
    st.caption("한국 인스타 무드 기반 AI 코디 추천")

    with st.sidebar:
        st.header("내 정보")
        gender = st.selectbox("성별", ["여성", "남성", "유니섹스"], index=["여성", "남성", "유니섹스"].index(st.session_state.profile["gender"]))
        style_pref = st.multiselect(
            "선호 스타일",
            inventory.style_tag_options(),
            default=st.session_state.profile.get("style_preferences", []),
        )
        season_pref = st.multiselect(
            "코디 희망 시즌",
            inventory.season_options(),
            default=st.session_state.profile.get("season", []),
        )
        budget = st.slider("1벌 예산 (만원)", min_value=5, max_value=60, value=int(st.session_state.profile.get("budget", 20)))
        _update_profile(gender, style_pref, season_pref, budget)

        if st.button("인벤토리 새로고침"):
            _refresh_inventory()

        st.divider()
        st.header("추천 데이터 설정")
        options = st.session_state.catalog_options
        limit_total = st.slider(
            "추천 아이템 목표 수 (전체)",
            min_value=20,
            max_value=240,
            step=10,
            value=int(options.get("limit_total", 120)),
            help="무신사·크림 데이터를 합쳐 최소 이 숫자 이상 노출하도록 시도해요.",
        )
        include_static = st.checkbox(
            "로컬 카탈로그 포함",
            value=bool(options.get("include_static", True)),
        )
        include_musinsa = st.checkbox(
            "무신사 데이터 포함",
            value=bool(options.get("include_musinsa", True)),
        )
        include_kream = st.checkbox(
            "크림 데이터 포함",
            value=bool(options.get("include_kream", True)),
        )
        refresh_static = st.checkbox(
            "내가 등록한 상품 실시간 업데이트",
            value=bool(options.get("refresh_static", True)),
            help="정적 카탈로그 항목을 무신사·크림 상품 페이지에서 실시간으로 갱신합니다",
        )
        per_category_input = st.number_input(
            "카테고리별 최대 추천 수 (0은 자동)",
            min_value=0,
            max_value=240,
            value=int(options.get("per_category_cap") or 0),
            step=5,
        )
        per_category_cap = per_category_input or None
        st.session_state.catalog_options.update(
            {
                "limit_total": limit_total,
                "include_static": include_static,
                "include_musinsa": include_musinsa,
                "include_kream": include_kream,
                "refresh_static": refresh_static,
                "per_category_cap": per_category_cap,
            }
        )

        with st.expander("계정 연동 (선택)"):
            st.caption(
                "브라우저에서 복사한 세션 쿠키를 입력하면 개인화된 상품과 장바구니 기반 추천까지 확장할 수 있어요."
            )
            st.markdown(
                """
                **무신사·크림 쿠키 입력 방법**
                1. Chrome(또는 Edge)에서 해당 사이트에 로그인한 뒤 상품 페이지를 엽니다.
                2. `F12` 키를 눌러 개발자 도구를 열고 **Application → Storage → Cookies** 메뉴로 이동합니다.
                3. 도메인을 선택한 후 `MUSINSA_SESSION`(무신사) 또는 `krem_session`(크림) 항목의 전체 값을 복사합니다.
                4. 아래 입력창에 붙여넣고 `Enter`를 눌러 저장하세요. 쿠키는 로컬 세션 상태에만 보관됩니다.
                """
            )
            st.info("사설 네트워크(VPN) 사용 시 국내 서버로 접속해야 정상 동작할 수 있어요.")
            musinsa_cookie = st.text_input(
                "무신사 세션 쿠키",
                value=st.session_state.integrations.get("musinsa_cookie", ""),
                type="password",
                help="예: 'MUSINSA_SESSION=...' 형식 전체를 붙여넣으세요.",
            )
            kream_cookie = st.text_input(
                "크림 세션 쿠키",
                value=st.session_state.integrations.get("kream_cookie", ""),
                type="password",
                help="예: 'krem_session=...' 형식 전체를 붙여넣으세요.",
            )
            st.session_state.integrations.update(
                {
                    "musinsa_cookie": musinsa_cookie.strip(),
                    "kream_cookie": kream_cookie.strip(),
                }
            )

    tab1, tab2, tab3 = st.tabs(["나의 옷장", "보유 코디", "추천 아이템"])

    with tab1:
        st.header("보유 의류 등록")
        with st.form("inventory_form"):
            col_left, col_right = st.columns(2)
            with col_left:
                name = st.text_input("아이템 이름")
                category = st.selectbox("카테고리", inventory.category_options())
                color = st.text_input("색상", placeholder="예: 아이보리")
            with col_right:
                season = st.multiselect("착용 시즌", inventory.season_options(), default=["사계절"])
                style_tags = st.multiselect("스타일 태그", inventory.style_tag_options())
                notes = st.text_area("메모", placeholder="특징이나 착용감을 기록하세요")

            image_file = st.file_uploader("이미지 업로드", type=["png", "jpg", "jpeg"])
            submitted = st.form_submit_button("저장")
            if submitted:
                if not name:
                    st.error("아이템 이름을 입력해 주세요")
                else:
                    inventory.add_item(
                        name=name,
                        category=category,
                        color=color,
                        season=season,
                        style_tags=style_tags,
                        image_file=image_file,
                        notes=notes,
                    )
                    st.success(f"{name}을(를) 옷장에 추가했어요")
                    _refresh_inventory()

        st.divider()
        st.subheader("내 옷장 리스트")
        _display_inventory_table(st.session_state.inventory_df)

    with tab2:
        st.header("보유 의류로 만드는 오늘의 코디")
        outfit_list = recommendations.outfit_suggestions(st.session_state.inventory_df, st.session_state.profile)
        if not outfit_list:
            st.info("코디를 생성하려면 신발과 함께 매치할 아이템을 옷장에 추가해주세요")
        else:
            for outfit in outfit_list:
                _render_outfit_card(outfit)

    with tab3:
        st.header("신규 아이템 추천")
        recommended, meta = recommendations.wishlist_suggestions(
            st.session_state.inventory_df,
            st.session_state.profile,
            limit_total=st.session_state.catalog_options.get("limit_total", 120),
            per_category_cap=st.session_state.catalog_options.get("per_category_cap"),
            include_static=st.session_state.catalog_options.get("include_static", True),
            include_musinsa=st.session_state.catalog_options.get("include_musinsa", True),
            include_kream=st.session_state.catalog_options.get("include_kream", True),
            musinsa_limit=st.session_state.catalog_options.get("limit_total", 120),
            kream_limit=st.session_state.catalog_options.get("limit_total", 120),
            musinsa_cookie=st.session_state.integrations.get("musinsa_cookie") or None,
            kream_cookie=st.session_state.integrations.get("kream_cookie") or None,
            refresh_static=st.session_state.catalog_options.get("refresh_static", False),
        )

        if meta.get("errors"):
            for error_msg in meta["errors"]:
                st.warning(error_msg)

            musinsa_failure = any("무신사" in msg for msg in meta["errors"])
            kream_failure = any("KREAM" in msg or "크림" in msg for msg in meta["errors"])

            if musinsa_failure and st.session_state.catalog_options.get("include_musinsa"):
                st.session_state.catalog_options["include_musinsa"] = False
                st.info("무신사 연결이 불안정하여 자동으로 비활성화했습니다. 네트워크를 확인한 후 사이드바에서 다시 켤 수 있어요.")

            if kream_failure and st.session_state.catalog_options.get("include_kream"):
                st.session_state.catalog_options["include_kream"] = False
                st.info("크림 연결이 불안정하여 자동으로 비활성화했습니다. 네트워크를 확인한 후 사이드바에서 다시 켤 수 있어요.")

        cap_value = meta.get("per_category_cap")
        cap_display = cap_value if cap_value else "자동"
        st.caption(
            f"후보 {meta.get('total_candidates', 0)}개 중 {meta.get('total_selected', 0)}개를 노출 중 (카테고리별 최대 {cap_display}개)"
        )
        if meta.get("source_counts"):
            source_summary = ", ".join(f"{key}: {value}개" for key, value in meta["source_counts"].items())
            st.caption(f"데이터 소스별 수집량 · {source_summary}")

        ordered_categories = [
            "상의",
            "아우터",
            "바지",
            "원피스",
            "스커트",
            "신발",
            "모자",
            "액세서리",
            "가방",
            "기타",
        ]
        available_categories = [cat for cat in ordered_categories if cat in recommended]
        extra_categories = [cat for cat in recommended.keys() if cat not in ordered_categories]
        available_categories.extend(extra_categories)
        if not available_categories:
            st.info("무신사/크림 카탈로그 기반 추천을 준비 중이에요")
            return

        tabs = st.tabs(available_categories)
        for category, tab in zip(available_categories, tabs):
            with tab:
                items = recommended.get(category, [])
                _render_product_grid(items)


if __name__ == "__main__":
    main()



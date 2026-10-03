"""Applying, checking and previewing chapter edits."""

from __future__ import annotations

import pytest

from story_construction_plugin.edits import (
    Edit,
    EditError,
    apply_edits,
    build_previews,
    check_edits,
    clean_body,
    edits_digest,
    parse_edits,
    text_digest,
)

BASE = "他推开门。\n\n雨下得很大，街上没有人。\n\n她在屋里等着。"


def _apply(raw, base=BASE):
    return apply_edits(base, parse_edits(raw))


def test_replace_swaps_exactly_one_unique_passage() -> None:
    result = _apply([{"op": "replace", "old_text": "雨下得很大", "new_text": "雨下得很急"}])

    assert result == "他推开门。\n\n雨下得很急，街上没有人。\n\n她在屋里等着。"


def test_replace_with_empty_text_deletes_the_passage() -> None:
    result = _apply([{"op": "replace", "old_text": "，街上没有人", "new_text": ""}])

    assert result == "他推开门。\n\n雨下得很大。\n\n她在屋里等着。"


def test_missing_text_is_rejected_with_the_edit_index() -> None:
    with pytest.raises(EditError) as error:
        _apply([
            {"op": "replace", "old_text": "雨下得很大", "new_text": "x"},
            {"op": "replace", "old_text": "不存在的句子", "new_text": "y"},
        ])

    assert error.value.code == "edit_not_found" and error.value.index == 1


def test_ambiguous_text_reports_how_often_it_appears() -> None:
    with pytest.raises(EditError) as error:
        _apply([{"op": "replace", "old_text": "。", "new_text": "！"}])

    assert error.value.code == "edit_ambiguous"
    assert error.value.details["matches"] == 3


def test_inserts_land_next_to_their_anchor() -> None:
    after = _apply([{"op": "insert_after", "anchor_text": "他推开门。", "new_text": "风灌了进来。"}])
    before = _apply([{"op": "insert_before", "anchor_text": "她在屋里等着。", "new_text": "灯还亮着。"}])

    assert after.startswith("他推开门。风灌了进来。")
    assert "灯还亮着。她在屋里等着。" in before


def test_append_and_prepend_start_a_new_paragraph() -> None:
    assert _apply([{"op": "append", "new_text": "天亮了。"}]).endswith("她在屋里等着。\n\n天亮了。")
    assert _apply([{"op": "prepend", "new_text": "序。"}]).startswith("序。\n\n他推开门。")
    assert _apply([{"op": "append", "new_text": "第一段。"}], base="") == "第一段。"


def test_later_edits_see_the_result_of_earlier_ones() -> None:
    result = _apply([
        {"op": "replace", "old_text": "他推开门。", "new_text": "他推开了旧木门。"},
        {"op": "replace", "old_text": "旧木门", "new_text": "吱呀作响的旧木门"},
    ])

    assert result.startswith("他推开了吱呀作响的旧木门。")


def test_a_failing_edit_leaves_nothing_applied() -> None:
    with pytest.raises(EditError):
        _apply([
            {"op": "replace", "old_text": "雨下得很大", "new_text": "雨很小"},
            {"op": "replace", "old_text": "没有这句", "new_text": "x"},
        ])
    # apply_edits works on a copy: the base text is a value, so it is unchanged.
    assert "雨下得很大" in BASE


def test_a_rewrite_replaces_everything_and_must_stand_alone() -> None:
    assert _apply([{"op": "rewrite", "content": "全新的正文。"}]) == "全新的正文。"
    with pytest.raises(EditError) as error:
        parse_edits([{"op": "rewrite", "content": "a"}, {"op": "append", "new_text": "b"}])
    assert error.value.code == "rewrite_must_be_alone"


def test_crlf_in_the_chapter_still_matches() -> None:
    result = _apply(
        [{"op": "replace", "old_text": "他推开门。\n\n雨", "new_text": "他进了门。\n\n雨"}],
        base=BASE.replace("\n", "\r\n"),
    )

    assert result.startswith("他进了门。\n\n雨下得很大")


@pytest.mark.parametrize("raw", [
    None, [], "text", [1], [{"op": "explode"}],
    [{"op": "replace", "old_text": "", "new_text": "x"}],
    [{"op": "replace", "old_text": "a"}],
    [{"op": "append", "new_text": ""}],
    [{"op": "append", "new_text": 5}],
])
def test_malformed_edit_lists_are_rejected(raw) -> None:
    with pytest.raises(EditError):
        parse_edits(raw)


def test_frontmatter_is_refused() -> None:
    with pytest.raises(EditError) as error:
        clean_body("---\nid: x\n---\n正文")

    assert error.value.code == "frontmatter_not_allowed"


def test_a_wrapping_code_fence_is_removed() -> None:
    cleaned, warnings = clean_body("```markdown\n夜深了。\n```")

    assert cleaned == "夜深了。"
    assert [w.kind for w in warnings] == ["fence_removed"]


@pytest.mark.parametrize("text", [
    "好的，这是修改后的版本：\n夜深了。",
    "当然！下面是改写：\n夜深了。",
    "以下是新的段落\n夜深了。",
    "Sure, here is the paragraph:\nIt was late.",
])
def test_lead_in_text_is_flagged_not_removed(text) -> None:
    cleaned, warnings = clean_body(text)

    assert cleaned == text
    assert "leading_guidance" in [w.kind for w in warnings]


@pytest.mark.parametrize("text", [
    "夜深了。\n希望这个版本符合你的要求。",
    "夜深了。\n如果需要调整，请告诉我。",
    "夜深了。\n需要我继续写下一段吗？",
    "It was late.\nLet me know if you want changes.",
])
def test_trailing_commentary_is_flagged(text) -> None:
    _cleaned, warnings = clean_body(text)

    assert "trailing_guidance" in [w.kind for w in warnings]


@pytest.mark.parametrize("text", [
    "夜深了。\n\n“好的，我们走吧。”他说。\n\n门关上了。",
    "“好的。”她说。\n夜深了。",
    "她说：希望明天会好。\n夜深了。",
    "夜深了。",
])
def test_ordinary_prose_is_not_flagged(text) -> None:
    _cleaned, warnings = clean_body(text)

    assert warnings == []


def test_a_heading_that_repeats_the_chapter_title_is_flagged() -> None:
    _cleaned, warnings = clean_body("# 第一章 雨夜\n\n夜深了。", title="第一章 雨夜")

    assert [w.kind for w in warnings] == ["duplicate_title"]
    assert clean_body("# 别的标题\n\n夜深了。", title="第一章 雨夜")[1] == []


def test_check_edits_cleans_every_edit_and_numbers_the_warnings() -> None:
    edits = parse_edits([
        {"op": "replace", "old_text": "雨下得很大", "new_text": "```\n雨很急\n```"},
        {"op": "append", "new_text": "天亮了。\n如需调整请告诉我。"},
    ])

    cleaned, warnings = check_edits(edits)

    assert cleaned[0].new_text == "雨很急"
    assert [(w.edit, w.kind) for w in warnings] == [(0, "fence_removed"), (1, "trailing_guidance")]


def test_previews_show_the_changed_paragraph_and_the_inline_change() -> None:
    edits = parse_edits([{"op": "replace", "old_text": "很大", "new_text": "很急"}])

    (preview,) = build_previews(BASE, edits)

    assert preview["op"] == "replace" and len(preview["regions"]) == 1
    region = preview["regions"][0]
    assert region["old"] == "雨下得很大，街上没有人。" and region["new"] == "雨下得很急，街上没有人。"
    assert region["line"] == 3
    assert [part["op"] for part in region["inline"]] == ["equal", "delete", "insert", "equal"]
    assert region["inline"][1]["text"] == "大" and region["inline"][2]["text"] == "急"


def test_the_inline_change_of_english_text_is_by_word() -> None:
    edits = parse_edits([{"op": "replace", "old_text": "squinting up at the grey morning",
                          "new_text": "peering up at the pewter morning"}])

    (preview,) = build_previews("She stood, squinting up at the grey morning.\n", edits)
    inline = preview["regions"][0]["inline"]

    assert [(part["op"], part["text"]) for part in inline if part["op"] != "equal"] == [
        ("delete", "squinting"), ("insert", "peering"), ("delete", "grey"), ("insert", "pewter"),
    ]
    old = "".join(part["text"] for part in inline if part["op"] in ("equal", "delete"))
    new = "".join(part["text"] for part in inline if part["op"] in ("equal", "insert"))
    assert old == preview["regions"][0]["old"] and new == preview["regions"][0]["new"]


def test_a_rewritten_phrase_is_one_change_not_alternating_words() -> None:
    edits = parse_edits([{
        "op": "replace", "old_text": "soaked to the bone. He was shielding",
        "new_text": "rain streaming from his hair and sleeves. He was holding",
    }])

    (preview,) = build_previews("On the step stood a young man, soaked to the bone. He was shielding a bundle.\n", edits)
    inline = preview["regions"][0]["inline"]

    assert [(part["op"], part["text"]) for part in inline if part["op"] != "equal"] == [
        ("delete", "soaked to the bone"), ("insert", "rain streaming from his hair and sleeves"),
        ("delete", "shielding"), ("insert", "holding"),
    ]


def test_each_chinese_character_is_still_its_own_unit() -> None:
    edits = parse_edits([{"op": "replace", "old_text": "雨下得很大", "new_text": "雨下得很急"}])

    (preview,) = build_previews("雨下得很大。\n", edits)
    inline = preview["regions"][0]["inline"]

    assert [(part["op"], part["text"]) for part in inline if part["op"] != "equal"] == [
        ("delete", "大"), ("insert", "急"),
    ]


def test_a_pure_insert_preview_has_no_old_text() -> None:
    edits = parse_edits([{"op": "append", "new_text": "天亮了。"}])

    (preview,) = build_previews(BASE, edits)

    assert any(region["inline"][-1] == {"op": "insert", "text": region["new"]} for region in preview["regions"])


def test_digests_ignore_line_endings_and_follow_the_content() -> None:
    assert text_digest("a\r\nb") == text_digest("a\nb")
    assert text_digest("a") != text_digest("b")
    first = parse_edits([{"op": "append", "new_text": "x"}])
    second = parse_edits([{"op": "append", "new_text": "y"}])
    assert edits_digest(first) == edits_digest(first) != edits_digest(second)


def test_edit_error_payload_carries_code_and_position() -> None:
    error = EditError("edit_ambiguous", "twice", index=2, matches=2)

    assert error.as_dict() == {"code": "edit_ambiguous", "message": "twice", "edit": 2, "matches": 2}
    assert Edit(op="append", new_text="x").as_dict() == {"op": "append", "new_text": "x"}


# ----------------------------------------------------------- tolerant matching
CURLY = "他说：“走吧”，然后离开了。\n\n她——没有回答。  \n\n天黑了。"


def test_straight_quotes_find_curly_quoted_text() -> None:
    result = _apply(
        [{"op": "replace", "old_text": '"走吧"，然后', "new_text": "他转身，然后"}],
        base=CURLY,
    )

    # Only the matched span changed; the text around it is untouched.
    assert result.startswith("他说：他转身，然后离开了。")
    assert result.endswith("天黑了。")


def test_dash_and_trailing_blank_differences_are_tolerated() -> None:
    dash = _apply([{"op": "replace", "old_text": "她--没有回答。", "new_text": "她点了头。"}], base=CURLY)
    anchored = _apply(
        [{"op": "insert_after", "anchor_text": "没有回答。", "new_text": "风停了。"}], base=CURLY
    )

    assert "她点了头。" in dash and "没有回答" not in dash
    assert "没有回答。风停了。" in anchored


def test_an_exact_match_is_preferred_over_a_tolerant_one() -> None:
    base = '甲“x”乙\n\n甲"x"乙'

    result = _apply([{"op": "replace", "old_text": '甲"x"乙', "new_text": "丙"}], base=base)

    assert result == "甲“x”乙\n\n丙"


def test_a_tolerant_match_that_hits_twice_is_still_ambiguous() -> None:
    both = "甲“x”乙\n\n甲“x”乙"

    with pytest.raises(EditError) as error:
        _apply([{"op": "replace", "old_text": '甲"x"乙', "new_text": "丙"}], base=both)

    assert error.value.code == "edit_ambiguous" and error.value.details["matches"] == 2


def test_full_width_punctuation_is_not_folded_to_half_width() -> None:
    with pytest.raises(EditError) as error:
        _apply([{"op": "replace", "old_text": "天黑了.", "new_text": "天亮了。"}], base="天黑了。")

    assert error.value.code == "edit_not_found"


def test_a_needle_of_only_blanks_never_matches_by_folding() -> None:
    with pytest.raises(EditError) as error:
        _apply([{"op": "replace", "old_text": "　", "new_text": "x"}], base="甲乙")

    assert error.value.code == "edit_not_found"


# ----------------------------------------------------------- previews of long texts
def _long_text(paragraphs: int, tag: str = "") -> str:
    return "\n\n".join(f"{tag}第{i}段：" + "雨" * 40 + f"{i}" for i in range(paragraphs))


def _rebuilt(region: dict) -> tuple[str, str]:
    old = "".join(part["text"] for part in region["inline"] if part["op"] in ("equal", "delete"))
    new = "".join(part["text"] for part in region["inline"] if part["op"] in ("equal", "insert"))
    return old, new


def test_a_small_change_in_a_long_text_is_one_region_at_the_right_line() -> None:
    base = _long_text(3000)
    (preview,) = build_previews(base, [Edit(op="replace", old_text="第1500段：", new_text="第一千五百段：")])

    (region,) = preview["regions"]
    assert region["line"] == 1500 * 2 + 1
    assert region["old"].startswith("第1500段：") and region["new"].startswith("第一千五百段：")
    assert _rebuilt(region) == (region["old"], region["new"])


def test_the_cut_off_head_and_tail_do_not_move_line_numbers_or_merge_regions() -> None:
    base = "甲\n乙\n丙\n丁\n戊\n己\n庚"
    edits = [
        Edit(op="replace", old_text="乙", new_text="乙乙"),
        Edit(op="replace", old_text="己", new_text="己己"),
    ]

    first, second = build_previews(base, edits)

    assert [(r["line"], r["old"], r["new"]) for r in first["regions"]] == [(2, "乙", "乙乙")]
    assert [(r["line"], r["old"], r["new"]) for r in second["regions"]] == [(6, "己", "己己")]


def test_two_separate_changes_in_one_edit_stay_two_regions() -> None:
    base = "一\n二\n三\n四\n五\n六\n七"
    after = base.replace("二", "2").replace("六", "6")

    (preview,) = build_previews(base, [Edit(op="rewrite", content=after)])

    assert [(r["line"], r["old"], r["new"]) for r in preview["regions"]] == [(2, "二", "2"), (6, "六", "6")]


def test_a_rewrite_of_a_very_long_text_is_fast_and_shown_as_one_region() -> None:
    import time

    base = _long_text(2000)
    rewritten = _long_text(2000, tag="新")

    started = time.perf_counter()
    (preview,) = build_previews(base, [Edit(op="rewrite", content=rewritten)])
    elapsed = time.perf_counter() - started

    (region,) = preview["regions"]
    assert region["line"] == 1 and region["old"] == base and region["new"] == rewritten
    assert elapsed < 5, elapsed  # matching every line pair took minutes before the cap


def test_unchanged_text_has_no_regions_and_a_pure_insert_keeps_its_line() -> None:
    base = "甲\n乙\n丙"

    assert build_previews(base, [Edit(op="replace", old_text="乙", new_text="乙")])[0]["regions"] == []
    (added,) = build_previews(base, [Edit(op="append", new_text="新")])
    assert [(r["line"], r["old"], r["new"]) for r in added["regions"]] == [(4, "", "\n新")]
    (inline,) = build_previews(base, [Edit(op="insert_after", anchor_text="乙", new_text="新")])
    assert [(r["line"], r["old"], r["new"]) for r in inline["regions"]] == [(2, "乙", "乙新")]

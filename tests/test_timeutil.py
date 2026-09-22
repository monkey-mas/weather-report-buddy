"""jst_date() が「入力側のタイムゾーンを答えに漏らさない」ことの回帰テスト。

元のコードは naive な datetime.now() を使っており、日付がプロセスの
タイムゾーンに従っていた。開発機が JST だったので手元では正しく見えるが、
UTC のコンテナでは 00:00-09:00 JST の間だけ前日の日付をプロンプトに渡す。
「手元では再現しない」種類のバグなので、実行環境に依存しない形で固定する。

バグの中身は「瞬間が同じでも、どのタイムゾーンで表現したかで答えが変わる」
ことなので、それをそのまま性質として書ける。例を1つ選んで固定するより、
任意の瞬間・任意のオフセットについて言うほうが素直なので @given にした。

不変性だけでは足りない（定数を返す実装でも通る）ので、絶対値を固定する例を
別に置いている。両方あって初めて「正しい日付を、環境に依らず返す」になる。

LLM も API キーも要らない。buddy.timeutil は設定を引かないので、
このテストは OPENAI_API_KEY 無しで動く（smoke test とはそこが違う）。
"""

from datetime import UTC, datetime, timedelta, timezone

import pytest
from hypothesis import given
from hypothesis import strategies as st

from buddy.timeutil import JST, jst_date

# 固定オフセットのタイムゾーン。ZoneInfo を使わないのは buddy/timeutil.py が
# JST を固定オフセットにしているのと同じ理由で、tzdata が入っていない環境でも
# 動かすため。datetime.timezone は ±24h 未満しか受け付けない。
_timezones = st.integers(min_value=-23 * 60, max_value=23 * 60).map(
    lambda minutes: timezone(timedelta(minutes=minutes))
)

# datetime.max / min の近傍は astimezone がオフセットぶんはみ出して
# OverflowError になる。上の ±23h より内側に寄せておけば踏まない。
# 見たいのは日付の跨ぎなので、範囲を限界まで広げる必要は無い。
_instants = st.datetimes(
    min_value=datetime(2, 1, 1, tzinfo=UTC),
    max_value=datetime(9998, 12, 31, tzinfo=UTC),
    timezones=st.just(UTC),
)


@given(instant=_instants, tz_a=_timezones, tz_b=_timezones)
def test_jst_date_ignores_how_the_instant_is_expressed(instant, tz_a, tz_b):
    """同じ瞬間なら、どのタイムゾーンで表現しても同じ日付になる。"""
    assert jst_date(instant.astimezone(tz_a)) == jst_date(instant.astimezone(tz_b))


@pytest.mark.parametrize(
    ("instant", "expected"),
    [
        # 15:00 UTC = 00:00 JST。ここが日付の変わり目。
        (datetime(2025, 12, 31, 14, 59, 59, tzinfo=UTC), "2025-12-31"),
        (datetime(2025, 12, 31, 15, 0, 0, tzinfo=UTC), "2026-01-01"),
        # 同じ瞬間を JST 表記で渡した場合。上の不変性の具体例でもある。
        (datetime(2026, 1, 1, 0, 0, 0, tzinfo=JST), "2026-01-01"),
    ],
)
def test_jst_date_turns_over_at_15_utc(instant, expected):
    assert jst_date(instant) == expected

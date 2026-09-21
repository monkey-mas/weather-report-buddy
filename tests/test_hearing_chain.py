"""hearing chain が LLM に渡す「今日」が JST 基準であることの回帰テスト。

元のコードは naive な datetime.now() を使っており、日付がプロセスの
タイムゾーンに従っていた。開発機が JST だったので手元では正しく見えるが、
UTC のコンテナでは 00:00-09:00 JST の間だけ前日の日付をプロンプトに渡す。
「手元では再現しない」種類のバグなので、実行環境に依存しない形で固定する。

LLM も API キーも要らない。hearing_chain の import は settings を引かないので、
このテストは OPENAI_API_KEY 無しで動く（smoke test とはそこが違う）。

private な _current_date_jst() を直接叩いている。本来の呼び出し口である
_run() は chain.invoke で LLM を呼ぶため、そこを入口にすると LLM のモックが
必要になり、確かめたいタイムゾーンの話より仕掛けのほうが大きくなる。
"""

from datetime import UTC, datetime

from buddy.agent.chains import hearing_chain
from buddy.timeutil import JST


def test_current_date_jst_uses_jst_not_process_timezone(monkeypatch):
    # 2025-12-31 15:30 UTC == 2026-01-01 00:30 JST。日付が跨るので、
    # どちらのタイムゾーンで見たかが返り値に現れる。
    instant = datetime(2025, 12, 31, 15, 30, tzinfo=UTC)
    captured = {}

    class _FixedNow(datetime):
        @classmethod
        def now(cls, tz=None):
            captured["tz"] = tz
            return instant.astimezone(tz)

    monkeypatch.setattr(hearing_chain, "datetime", _FixedNow)

    assert hearing_chain._current_date_jst() == "2026-01-01"

    # 渡した tz そのものも見る。これが無いと、naive な now() に戻してしまった
    # ときに astimezone(None) がローカル時刻へ変換するため、JST のマシンでは
    # 上の assert が通ってしまう。CI (UTC) でだけ落ちる状態になり、今直した
    # バグと同じ「手元では再現しない」構図をテスト自身が繰り返す。
    assert captured["tz"] is JST

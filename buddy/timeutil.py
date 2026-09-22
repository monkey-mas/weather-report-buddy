"""アプリ全体で共有する時刻まわりの定数。

JST をここに置くのは、これが特定の機能の概念ではなく「このアプリは日本でしか
使わない」というアプリ全体の前提だから。tools/radar.py に置いていたときは、
レーダーと無関係なモジュール（今日の日付を LLM に渡したいだけの hearing chain）
がタイル取得モジュールを import する必要があり、依存の向きが説明しづらかった。

ZoneInfo("Asia/Tokyo") ではなく固定オフセットにしている。JST に夏時間は無いので
両者は一致し、固定オフセットなら tzdata が入っていない環境でも動く。
"""

from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))


def jst_date(t: datetime) -> str:
    """aware な時刻 t を、JST から見た日付の文字列にする。

    「時計を読む」ことと「読んだ値を JST の日付に直す」ことを分けている。
    後者だけを取り出すと入力を引数で渡せるので、時計を差し替えずに
    任意の瞬間について検証できる（tests/test_timeutil.py）。

    分けたことで、呼び出し側が now() にどのタイムゾーンを渡していても
    結果が変わらなくなる。以前ここが一体だったときは「JST を渡し忘れる」
    ことが日付のずれに直結していた。残る前提は t が aware であることだけで、
    そこは ruff の DTZ が押さえる。

    t は aware であること。astimezone は naive をローカル時刻とみなすので、
    naive を渡すと結果が実行環境に依存する（まさに直したかったバグの形）。
    """
    return t.astimezone(JST).strftime("%Y-%m-%d")

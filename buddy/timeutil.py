"""アプリ全体で共有する時刻まわりの定数。

JST をここに置くのは、これが特定の機能の概念ではなく「このアプリは日本でしか
使わない」というアプリ全体の前提だから。tools/radar.py に置いていたときは、
レーダーと無関係なモジュール（今日の日付を LLM に渡したいだけの hearing chain）
がタイル取得モジュールを import する必要があり、依存の向きが説明しづらかった。

ZoneInfo("Asia/Tokyo") ではなく固定オフセットにしている。JST に夏時間は無いので
両者は一致し、固定オフセットなら tzdata が入っていない環境でも動く。
"""

from datetime import timedelta, timezone

JST = timezone(timedelta(hours=9))

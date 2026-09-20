from dataclasses import asdict
from typing import Literal

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt

from buddy.agent.chains.analyze_chain import AnalyzeChain
from buddy.agent.chains.hearing_chain import HearingChain
from buddy.agent.chains.resolve_chain import ResolveChain
from buddy.agent.state import AgentState, GeoResult, InputState, OutputState
from buddy.settings import settings
from buddy.tools.geocode import nominatim_geocode, web_search
from buddy.tools.radar import fetch_nowcast


class WeatherBuddyAgent:
    """場所ヒアリング → 緯度経度解決 → 雨雲レーダー取得 → 分析アドバイス"""

    def __init__(self) -> None:
        llm = settings.llm
        self.hearing = HearingChain(llm)
        self.resolve = ResolveChain(llm)
        self.analyze = AnalyzeChain(settings.vision_llm)
        self.graph: CompiledStateGraph = self._build()

    def _build(self) -> CompiledStateGraph:
        g = StateGraph(
            state_schema=AgentState, input=InputState, output=OutputState
        )
        g.add_node("user_hearing", self.hearing)
        g.add_node("human_feedback", self._human_feedback)
        g.add_node("search_location", self._search_location)
        g.add_node("resolve", self.resolve)
        g.add_node("fetch_radar", self._fetch_radar)
        g.add_node("analyze", self.analyze)

        g.set_entry_point("user_hearing")
        return g.compile(checkpointer=MemorySaver())

    @staticmethod
    def _human_feedback(state: AgentState) -> Command[Literal["user_hearing"]]:
        # interrupt でユーザー入力を待つ。UI 側で Command(resume=...) で再開。
        question = state.get("ask_user", "追加情報を教えてください。")
        user_reply = interrupt(question)
        if not user_reply:
            user_reply = "そのまま最も一般的な解釈で構いません。"
        return Command(
            goto="user_hearing",
            update={"messages": [{"role": "human", "content": user_reply}]},
        )

    @staticmethod
    def _search_location(state: AgentState) -> Command[Literal["resolve"]]:
        query = state.get("original_query", "")
        candidates = nominatim_geocode(query, limit=5)

        web_hits: list[dict] = []
        # 候補が薄い or 見つからない場合は Web 検索も併用（通称対応）
        if len(candidates) <= 1:
            hits = web_search(f"{query} とは 場所 住所", max_results=5)
            web_hits = [
                {k: h.get(k) for k in ("title", "href", "body")} for h in hits
            ]
            # web の上位ヒットタイトルで再 geocode を試みる
            for h in hits[:2]:
                title = (h.get("title") or "").strip()
                if title and title != query:
                    extra = nominatim_geocode(title, limit=3)
                    candidates.extend(extra)

        return Command(
            goto="resolve",
            update={
                "candidates": [asdict(c) for c in candidates],
                "web_hits": web_hits,
            },
        )

    @staticmethod
    def _fetch_radar(state: AgentState) -> Command[Literal["analyze"]]:
        result: GeoResult = state["result"]
        radar = fetch_nowcast(result.lat, result.lon, out_root=settings.output_dir)
        if not radar.frames:
            raise RuntimeError("雨雲レーダー画像を1コマも取得できませんでした")

        frames = [
            {
                "offset_min": f.offset_min,
                "validtime": f.validtime,
                "path": str(f.composite_path),
            }
            for f in radar.frames
        ]
        msg = (
            f"雨雲レーダーを取得しました"
            f"（基準時刻 {radar.basetime_jst:%m-%d %H:%M} JST / {len(frames)}コマ）。"
            f"分析中..."
        )
        return Command(
            goto="analyze",
            update={
                "radar_basetime": radar.basetime,
                "radar_frames": frames,
                "messages": [{"role": "assistant", "content": msg}],
            },
        )


agent = WeatherBuddyAgent().graph

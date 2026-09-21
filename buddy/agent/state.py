from __future__ import annotations

from typing import Annotated, TypedDict

from langgraph.graph.message import AnyMessage, add_messages
from pydantic import BaseModel, Field


class GeoResult(BaseModel):
    """地名解決の結果 (緯度経度)"""

    query: str = Field(..., description="ユーザーの元の入力")
    resolved_name: str = Field(..., description="採用した地点の正式名称")
    lat: float = Field(..., description="緯度 (WGS84)")
    lon: float = Field(..., description="経度 (WGS84)")
    reasoning: str = Field(..., description="なぜこの地点を選んだかの説明")


class WeatherAdvice(BaseModel):
    """雨雲レーダー分析の結果"""

    advice: str = Field(
        ..., description="ユーザー向けの外出アドバイス(結論のみ、1〜2文)"
    )
    rationale: str = Field(
        ..., description="アドバイスの根拠(雨雲の位置・移動・強度の変化)"
    )


class InputState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]


class PrivateState(TypedDict, total=False):
    original_query: str
    candidates: list[dict]  # nominatim + web 由来の候補 (dict 化)
    web_hits: list[dict]  # web 検索結果
    need_feedback: bool
    ask_user: str  # ユーザーへの問い返し文


class OutputState(TypedDict, total=False):
    result: GeoResult | None
    radar_basetime: str  # 基準時刻 (UTC "yyyymmddHHMMSS")
    radar_frames: list[dict]  # {"offset_min": int, "validtime": str, "path": str}
    advice: WeatherAdvice | None


class AgentState(InputState, PrivateState, OutputState):
    pass

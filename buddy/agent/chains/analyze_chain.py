"""雨雲レーダー時系列画像を Vision LLM で分析して外出アドバイスを生成する。

既存スクリプトのプロンプトと構造化出力を、urllib 直叩きから
langchain-openai へ移植したもの。
"""

import base64
from pathlib import Path
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langgraph.types import Command

from buddy.agent.state import WeatherAdvice
from buddy.tools.radar import JST, parse_t


def _load_prompt(name: str) -> str:
    return (Path(__file__).parent / "prompts" / f"{name}.prompt").read_text().strip()


class AnalyzeChain:
    def __init__(self, llm: ChatOpenAI, detail: str = "high") -> None:
        self.llm = llm
        self.detail = detail

    def __call__(self, state: dict) -> Command[Literal["__end__"]]:
        frames = state.get("radar_frames", [])
        if not frames:
            raise RuntimeError("雨雲レーダー画像がありません")

        advice = self._run(frames)
        final_msg = f"{advice.advice}\n\n**根拠**: {advice.rationale}"
        return Command(
            goto="__end__",
            update={
                "advice": advice,
                "messages": [{"role": "assistant", "content": final_msg}],
            },
        )

    def _run(self, frames: list[dict]) -> WeatherAdvice:
        t0 = parse_t(frames[0]["validtime"]).astimezone(JST)
        content: list[dict] = [
            {
                "type": "text",
                "text": f"以下は {t0:%Y-%m-%d %H:%M} 時点を起点とした雨雲レーダーの時系列画像"
                f"({len(frames)}枚, 10分間隔)です。これから1時間の外出アドバイスをください。",
            }
        ]
        for f in frames:
            dt = parse_t(f["validtime"]).astimezone(JST)
            off = f["offset_min"]
            label = "現在(実況)" if off == 0 else f"+{off}分後の予報"
            content.append({"type": "text", "text": f"--- {dt:%H:%M} {label} ---"})
            b64 = base64.b64encode(Path(f["path"]).read_bytes()).decode()
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/png;base64,{b64}",
                        "detail": self.detail,
                    },
                }
            )

        chain = self.llm.with_structured_output(WeatherAdvice, method="json_schema")
        return chain.invoke(
            [
                SystemMessage(content=_load_prompt("analyze")),
                HumanMessage(content=content),
            ]
        )

from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from langgraph.types import Command
from pydantic import BaseModel, Field

from buddy.timeutil import jst_date


def _load_prompt(name: str) -> str:
    return (Path(__file__).parent / "prompts" / f"{name}.prompt").read_text().strip()


def _current_date_jst() -> str:
    """プロンプトの {current_date} に渡す「今日」。

    naive な datetime.now() はプロセスのタイムゾーンに従う。手元では JST の
    マシンで動かしていたので正しく見えていたが、UTC のコンテナに載せると
    00:00-09:00 JST の間だけ前日の日付を LLM に渡す。この値は会話中の
    「明日」のような相対表現を解釈させるためのものなので、ずれると場所では
    なく日付の解釈を静かに間違える。

    ナウキャストは日本国内しか覆わず、利用者の「今日」は常に JST。

    now() に渡すのが UTC なのは、jst_date が受け取った時刻を JST へ直すので
    どの aware なタイムゾーンでも結果が同じになるため。ここで JST を渡し忘れる
    ことが上のバグだったので、渡す値が結果を左右しない形にしてある。
    """
    # TODO: プロンプト側は「現在日時」と書いているが、渡しているのは日付だけで
    # 時刻が無い。「今から1時間後」のような相対表現を解釈させたいなら情報が
    # 足りない。時刻まで渡すか、プロンプトの文言を「現在日付」に寄せるか、
    # どちらかに揃える必要がある。プロンプト設計の判断なので保留。
    return jst_date(datetime.now(UTC))


class Hearing(BaseModel):
    is_need_human_feedback: bool = Field(default=False, description="追加質問が必要か")
    additional_question: str = Field(
        default="", description="ユーザーへの追加質問（不要なら空文字）"
    )
    normalized_query: str = Field(
        default="",
        description="検索に使うために正規化した地点名（例: 『109』→『渋谷 109』）。曖昧なら空文字。",
    )


class HearingChain:
    def __init__(self, llm: ChatOpenAI) -> None:
        self.llm = llm

    def __call__(
        self, state: dict
    ) -> Command[Literal["human_feedback", "search_location"]]:
        messages = state.get("messages", [])
        hearing = self._run(messages)

        if hearing.is_need_human_feedback:
            return Command(
                goto="human_feedback",
                update={
                    "need_feedback": True,
                    "ask_user": hearing.additional_question,
                    "messages": [
                        {"role": "assistant", "content": hearing.additional_question}
                    ],
                },
            )

        # 直近の human メッセージを原クエリとして採用
        original = next(
            (
                m.content
                for m in reversed(messages)
                if getattr(m, "type", "") == "human"
            ),
            "",
        )
        return Command(
            goto="search_location",
            update={
                "need_feedback": False,
                "original_query": hearing.normalized_query or original,
            },
        )

    def _run(self, messages: list[BaseMessage]) -> Hearing:
        prompt = ChatPromptTemplate.from_template(_load_prompt("hearing"))
        chain = prompt | self.llm.with_structured_output(
            Hearing, method="function_calling"
        )
        return chain.invoke(
            {
                "current_date": _current_date_jst(),
                "conversation_history": self._format(messages),
            }
        )

    @staticmethod
    def _format(messages: list[BaseMessage]) -> str:
        return "\n".join(
            f"{m.type}: {m.content}" for m in messages if getattr(m, "content", None)
        )

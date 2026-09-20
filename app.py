"""Streamlit UI: 場所を聞いて雨雲レーダー(今後60分)を分析し、外出アドバイスを返す"""
from __future__ import annotations

import uuid

import streamlit as st
from langchain_core.messages import HumanMessage
from langgraph.types import Command

from buddy.agent.graph import agent
from buddy.tools.radar import JST, parse_t

PROMPT_TEXT = "雨雲レーダーを確認したい場所を教えて"


def init_session() -> None:
    st.session_state.setdefault("messages", [])
    st.session_state.setdefault("thread_id", str(uuid.uuid4()))
    st.session_state.setdefault("waiting_feedback", False)
    st.session_state.setdefault("pending_question", "")
    st.session_state.setdefault("final_result", None)
    st.session_state.setdefault("radar_frames", None)
    st.session_state.setdefault("frame_idx", 0)
    st.session_state.setdefault("advice", None)
    st.session_state.setdefault("error", None)


def reset_session() -> None:
    st.session_state.messages = []
    st.session_state.thread_id = str(uuid.uuid4())
    st.session_state.waiting_feedback = False
    st.session_state.pending_question = ""
    st.session_state.final_result = None
    st.session_state.radar_frames = None
    st.session_state.frame_idx = 0
    st.session_state.advice = None
    st.session_state.error = None


def run_agent(input_data) -> None:
    st.session_state.error = None
    config = {"configurable": {"thread_id": st.session_state.thread_id}}
    with st.spinner("エージェント処理中...（レーダー取得・分析には1分ほどかかることがあります）"):
        try:
            for chunk in agent.stream(input_data, stream_mode="updates", config=config):
                for node_name, update in chunk.items():
                    if node_name == "__interrupt__":
                        # interrupt() の第一引数がタプルで届く
                        st.session_state.waiting_feedback = True
                        st.session_state.pending_question = update[0].value
                        continue
                    if not isinstance(update, dict):
                        continue
                    for m in update.get("messages", []) or []:
                        # LangGraph が dict 化する場合と AnyMessage の場合の両対応
                        role = m.get("role") if isinstance(m, dict) else getattr(m, "type", "assistant")
                        content = m.get("content") if isinstance(m, dict) else getattr(m, "content", "")
                        if role in ("assistant", "ai") and content:
                            st.session_state.messages.append(
                                {"role": "assistant", "content": content}
                            )
                    if update.get("result"):
                        st.session_state.final_result = update["result"]
                    if update.get("radar_frames"):
                        st.session_state.radar_frames = update["radar_frames"]
                    if update.get("advice"):
                        st.session_state.advice = update["advice"]
        except Exception as e:
            # st.rerun() で消えないよう session_state に保存して main() で表示する
            st.session_state.error = f"{type(e).__name__}: {e}"


def _frame_label(frame: dict) -> str:
    dt = parse_t(frame["validtime"]).astimezone(JST)
    off = frame["offset_min"]
    return f"{dt:%H:%M} " + ("現在(実況)" if off == 0 else f"+{off}分後の予報")


def render_radar_player() -> None:
    """気象庁の雨雲レーダー風のコマ送りプレイヤー(画像 + プログレスバー + 時刻)"""
    frames = st.session_state.radar_frames
    if not frames:
        return
    n = len(frames)

    st.markdown("**🌧️ 雨雲レーダー（現在〜+60分 / 10分間隔）**")
    playing = st.toggle("コマ送り再生", value=True, key="radar_playing")

    # 再生中は run_every で fragment だけが再実行され、1コマずつ進む
    @st.fragment(run_every=0.8 if (playing and n > 1) else None)
    def player() -> None:
        if playing:
            idx = st.session_state.frame_idx % n
        else:
            labels = [_frame_label(f) for f in frames]
            chosen = st.select_slider(
                "表示コマ", options=labels,
                value=labels[st.session_state.frame_idx % n],
                label_visibility="collapsed",
            )
            idx = labels.index(chosen)
            st.session_state.frame_idx = idx

        st.image(frames[idx]["path"], width="stretch")
        st.progress((idx + 1) / n, text=_frame_label(frames[idx]))

        if playing:
            st.session_state.frame_idx = (idx + 1) % n

    player()


def render_results() -> None:
    r = st.session_state.final_result
    if r:
        st.subheader(f"📍 {r.resolved_name}")
        col1, col2 = st.columns(2)
        col1.metric("緯度", f"{r.lat:.6f}")
        col2.metric("経度", f"{r.lon:.6f}")
        st.caption(f"選定理由: {r.reasoning}")

    render_radar_player()

    advice = st.session_state.advice
    if advice:
        st.success(f"☔ **{advice.advice}**")
        st.caption(f"根拠: {advice.rationale}")


def main() -> None:
    st.set_page_config(page_title="Weather Report Buddy", page_icon="🌦️")
    st.title("🌦️ Weather Report Buddy")
    st.caption("場所を教えてもらえたら、今後60分の雨雲レーダーを分析して外出アドバイスをします")

    init_session()

    # サイドバー
    with st.sidebar:
        st.subheader("操作")
        if st.button("会話をリセット", width="stretch"):
            reset_session()
            st.rerun()

    # 直前の実行で発生したエラー（st.rerun() 後もここで表示される）
    if st.session_state.error:
        st.error(f"エラー: {st.session_state.error}")

    # メッセージ履歴
    for msg in st.session_state.messages:
        st.chat_message(msg["role"]).write(msg["content"])

    # 結果表示（緯度経度・レーダー画像・アドバイス）
    render_results()

    # フィードバック待ち または 新規入力
    if st.session_state.waiting_feedback:
        st.info(f"❓ {st.session_state.pending_question}")
        reply = st.chat_input("回答を入力")
        if reply:
            st.session_state.messages.append({"role": "user", "content": reply})
            st.session_state.waiting_feedback = False
            st.session_state.pending_question = ""
            run_agent(Command(resume=reply))
            st.rerun()
    else:
        user_input = st.chat_input(PROMPT_TEXT)
        if user_input:
            # 新規セッション開始
            reset_session()
            st.session_state.messages.append({"role": "user", "content": user_input})
            run_agent({"messages": [HumanMessage(content=user_input)]})
            st.rerun()


if __name__ == "__main__":
    main()

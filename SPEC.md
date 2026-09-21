# weather-report-buddy — Specification

English | [日本語](SPEC.ja.md)

## Overview

An agent app that takes a place from the user, fetches and analyses the Japan Meteorological Agency high-resolution precipitation nowcast (高解像度降水ナウキャスト — rain radar covering the next 60 minutes) for that point, and returns practical advice: whether an umbrella is needed, when to leave.

## UI

- **Streamlit chat UI** (`st.chat_message` / `st.chat_input`)
- Conversation flow:
  1. the assistant asks for a place
  2. the user gives one (nothing proceeds until they do)
  3. if the place is ambiguous, the assistant asks back (e.g. "Fuchu (府中市) — the one in Tokyo, or the one in Hiroshima?")
  4. once the place is settled, the coordinates, the composited radar frames and the advice are shown in the chat

## Architecture

- An agent graph built on **LangGraph**

Routing is not expressed as static edges; each node returns `Command(goto=...)`.

```
START           ──→ user_hearing
user_hearing    ──→ human_feedback   (input is ambiguous)
user_hearing    ──→ search_location  (input is clear)
human_feedback  ──→ user_hearing     (always returns here, whichever node suspended)
search_location ──→ resolve          (candidates from Nominatim, plus a web search if needed)
resolve         ──→ human_feedback   (cannot narrow down to a single candidate)
resolve         ──→ fetch_radar      (one coordinate settled)
fetch_radar     ──→ analyze          (composited frames, now → +60 min in 10-minute steps)
analyze         ──→ END              (advice / rationale rendered in the UI)
```

There are **two** nodes that can raise `interrupt()`: `user_hearing` and `resolve`.
`human_feedback` returns to `user_hearing` regardless of which one suspended, so a
clarification originating in `resolve` re-runs the ambiguity check.

## Step specifications

### 1. Place hearing (user_hearing / human_feedback)
- An LLM (gpt-4o-mini) judges whether the input is ambiguous. If it is, `interrupt()` returns a question to the user and waits for the reply
- No downstream step runs until a place has been given

### 2. Geocoding (search_location / resolve)
- Nominatim (OpenStreetMap) supplies coordinate candidates (throttled to 1 req/sec; an identifying User-Agent is required by its usage policy)
- When candidates are thin, a DuckDuckGo search (`ddgs`) resolves a nickname to a formal place name
- An LLM picks the single best candidate and records its reasoning
- If it cannot narrow down to one, it asks the user back via `interrupt()` (`need_more_info`)

### 3. Radar fetch (fetch_radar)
- Fetches PNG tiles of the JMA nowcast (`product=nowc`, `element=hrpns`)
- Converts latitude/longitude to Web Mercator tile coordinates and mosaics the tiles
- Range: now → +60 min, in 10-minute steps (7 frames)
- Output: images composited over the base map, with a current-location marker, saved under `output/`

### 4. Analysis and advice (analyze)
- The composited frames are sent Base64-encoded to an OpenAI vision model (gpt-5-mini)
- The system prompt covers the precipitation intensity legend (降水強度凡例), giving priority to the current-location marker, and analysing the direction of movement
- Structured into Structured Outputs:
  - `advice`: the conclusion for the user (1-2 sentences; umbrella or not, adjusting departure time)
  - `rationale`: the grounds (1-3 sentences; position, movement and change in intensity of the rain)

## Models

| Purpose | Model |
|---|---|
| Ambiguity judgement / candidate selection | gpt-4o-mini |
| Radar image analysis | gpt-5-mini |

- Runs on a single OpenAI API key, managed in `.env` (`OPENAI_API_KEY`)

## Out of scope

- Long-range forecasts (rasrf / 15 hours ahead)
- Weather data other than the nowcast (temperature, warnings)
- Persisting conversation history; watching several locations at once

## Tech stack

- Python 3.11+ / uv (`pyproject.toml`)
- streamlit, langgraph, langchain-openai, langchain-core, pydantic, pydantic-settings, httpx, ddgs, python-dotenv, Pillow

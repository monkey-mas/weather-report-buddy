"""気象庁 高解像度降水ナウキャストの取得・地図合成。

既存の CLI スクリプトの nowcast 部分を、CLI 引数依存を外して関数 API として移植。
現在〜+60分(10分刻み)の雨雲レーダーを地理院地図に重ねた合成画像を生成する。

気象庁API仕様のポイント:
- タイルURL: .../jmatile/data/{product}/{basetime}/{member}/{validtime}/surf/{element}/{z}/{x}/{y}.png
- nowcast は product=nowc, element=hrpns, member=none 固定
- 取得可能な (basetime, validtime) は targetTimes_N1/N2.json で事前確認する
- 雨が1ピクセルも無いタイルは公開されず 404 になる → 透明として扱う(正常ケース)
- 実況(N1)が予報(N2)より先に公開されるレースがあるため、基準時刻は
  「予報(N2)が存在する最新の basetime」から選ぶ
"""

from __future__ import annotations

import io
import json
import math
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, UTC
from pathlib import Path

import httpx
from PIL import Image, ImageDraw

from buddy.timeutil import JST

TILE_SIZE = 256
RADAR_MAX_ZOOM = 10  # 雨雲タイルのネイティブ最大ズーム

JMA_TIMES_URL = "https://www.jma.go.jp/bosai/jmatile/data/{path}"
JMA_TILE_URL = (
    "https://www.jma.go.jp/bosai/jmatile/data/nowc/"
    "{basetime}/none/{validtime}/surf/hrpns/{z}/{x}/{y}.png"
)
GSI_TILE_URL = "https://cyberjapandata.gsi.go.jp/xyz/{style}/{z}/{x}/{y}.png"
UA = "weather-report-buddy/0.1 (personal use)"


@dataclass
class RadarFrame:
    offset_min: int  # 基準時刻からのオフセット(分)。0 は実況
    validtime: str  # UTC "yyyymmddHHMMSS"
    composite_path: Path  # 地図+雨雲+現在地マーカーの合成画像

    @property
    def time_jst(self) -> datetime:
        return parse_t(self.validtime).astimezone(JST)


@dataclass
class RadarResult:
    basetime: str  # 基準時刻 (UTC "yyyymmddHHMMSS")
    frames: list[RadarFrame]
    missing_offsets: list[int]  # データ未公開だったオフセット(分)

    @property
    def basetime_jst(self) -> datetime:
        return parse_t(self.basetime).astimezone(JST)


def parse_t(s: str) -> datetime:
    return datetime.strptime(s, "%Y%m%d%H%M%S").replace(tzinfo=UTC)


def offset_t(bt: str, minutes: int) -> str:
    return (parse_t(bt) + timedelta(minutes=minutes)).strftime("%Y%m%d%H%M%S")


def http_get(url: str) -> bytes:
    resp = httpx.get(url, headers={"User-Agent": UA}, timeout=30.0)
    resp.raise_for_status()
    return resp.content


def deg2pixel(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """緯度経度 → Webメルカトルのグローバルピクセル座標"""
    n = 2.0**zoom * TILE_SIZE
    x = (lon + 180.0) / 360.0 * n
    rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(rad) + 1.0 / math.cos(rad)) / math.pi) / 2.0 * n
    return x, y


def fetch_tiles(
    url_fmt: str, z: int, xs: range, ys: range, quiet_404: bool = False, **kw
) -> Image.Image:
    """タイル群を並列取得して1枚に結合(RGBA)。欠損タイルは透明のまま。

    quiet_404=True は雨雲タイル用: 雨の無いタイルは公開されず 404 になるため、
    404 は正常ケースとして透明扱いする。
    """
    mosaic = Image.new("RGBA", (len(xs) * TILE_SIZE, len(ys) * TILE_SIZE), (0, 0, 0, 0))

    def one(pos):
        i, x, j, y = pos
        url = url_fmt.format(z=z, x=x, y=y, **kw)
        try:
            img = Image.open(io.BytesIO(http_get(url))).convert("RGBA")
            return i, j, img
        except httpx.HTTPStatusError as e:
            if not (e.response.status_code == 404 and quiet_404):
                raise RuntimeError(f"タイル取得失敗: {url} ({e})") from e
            return i, j, None

    jobs = [(i, x, j, y) for j, y in enumerate(ys) for i, x in enumerate(xs)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        for i, j, img in ex.map(one, jobs):
            if img:
                mosaic.paste(img, (i * TILE_SIZE, j * TILE_SIZE))
    return mosaic


def select_frames_nowcast(
    n1: list[dict], n2: list[dict], interval: int, ahead: int
) -> tuple[str, list[tuple[int, str]], list[int]]:
    """ナウキャストの取得コマ (offset, validtime) を決定する。

    基準時刻は「予報(N2)が存在する最新の basetime」。N1 だけが先に公開される
    レース時に予報コマが全滅するのを防ぐ(基準が1コマ古くなることはある)。
    """
    ref = max(t["basetime"] for t in n2)
    available = {t["validtime"] for t in n1 + n2 if t["basetime"] == ref}

    frames, missing = [], []
    for off in range(0, ahead + 1, interval):
        vt = offset_t(ref, off)
        if vt in available:
            frames.append((off, vt))
        else:
            missing.append(off)
    return ref, frames, missing


def fetch_nowcast(
    lat: float,
    lon: float,
    out_root: str | Path = "output",
    zoom: int = 14,  # 徒歩移動の範囲感(3タイルで約7km四方)
    tiles: int = 3,
    interval: int = 10,
    ahead: int = 60,
    alpha: float = 0.7,
    style: str = "pale",
) -> RadarResult:
    """指定地点のナウキャスト合成画像(現在〜+ahead分)を生成して保存する。

    Returns:
        RadarResult (合成画像パスのリスト付き)
    """
    n1 = json.loads(http_get(JMA_TIMES_URL.format(path="nowc/targetTimes_N1.json")))
    n2 = json.loads(http_get(JMA_TIMES_URL.format(path="nowc/targetTimes_N2.json")))
    ref, frame_times, missing = select_frames_nowcast(n1, n2, interval, ahead)

    # --- タイル範囲の計算 ---
    half = tiles // 2
    px, py = deg2pixel(lat, lon, zoom)
    xc, yc = int(px // TILE_SIZE), int(py // TILE_SIZE)
    xs = range(xc - half, xc + half + 1)
    ys = range(yc - half, yc + half + 1)
    W = H = tiles * TILE_SIZE
    # 画像内での中心点(現在地マーカー)位置
    mx, my = int(px - xs[0] * TILE_SIZE), int(py - ys[0] * TILE_SIZE)

    loc_dir = Path(out_root) / f"{lat:.4f}_{lon:.4f}_z{zoom}x{tiles}"
    outdir = loc_dir / f"nowcast_{ref}"
    outdir.mkdir(parents=True, exist_ok=True)

    # --- 地図: basetime に依存しないため位置ディレクトリに1枚のみ ---
    map_path = loc_dir / "map.png"
    if map_path.exists():
        base = Image.open(map_path).convert("RGBA")
    else:
        base = fetch_tiles(GSI_TILE_URL, zoom, xs, ys, style=style)
        base.save(map_path)

    # --- 雨雲タイル: ネイティブ zoom で取得し、地図 zoom に合わせて拡大 ---
    zr = min(zoom, RADAR_MAX_ZOOM)
    d = zoom - zr
    rxs = range(xs[0] >> d, (xs[-1] >> d) + 1)
    rys = range(ys[0] >> d, (ys[-1] >> d) + 1)
    cx0 = (xs[0] * TILE_SIZE >> d) - rxs[0] * TILE_SIZE
    cy0 = (ys[0] * TILE_SIZE >> d) - rys[0] * TILE_SIZE
    crop_box = (cx0, cy0, cx0 + (W >> d), cy0 + (H >> d))

    frames: list[RadarFrame] = []
    for off, vt in frame_times:
        radar = fetch_tiles(
            JMA_TILE_URL, zr, rxs, rys, quiet_404=True, basetime=ref, validtime=vt
        )
        if d > 0:
            radar = radar.crop(crop_box).resize((W, H), Image.NEAREST)

        # 合成: 雨雲のアルファを調整して地図に重ね、現在地に赤十字マーカー
        overlay = radar.copy()
        overlay.putalpha(overlay.getchannel("A").point(lambda a: int(a * alpha)))
        comp = Image.alpha_composite(base, overlay)
        draw = ImageDraw.Draw(comp)
        draw.line([(mx - 10, my), (mx + 10, my)], fill=(255, 0, 0, 255), width=2)
        draw.line([(mx, my - 10), (mx, my + 10)], fill=(255, 0, 0, 255), width=2)

        path = outdir / f"composite_{vt}.png"
        comp.convert("RGB").save(path)
        frames.append(RadarFrame(offset_min=off, validtime=vt, composite_path=path))

    return RadarResult(basetime=ref, frames=frames, missing_offsets=missing)

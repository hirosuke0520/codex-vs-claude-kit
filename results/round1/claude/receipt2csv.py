#!/usr/bin/env python3
"""receipt2csv — 領収書（PDF・画像）のフォルダから file,date,amount,store の CSV を作る。

使い方:
    python3 receipt2csv.py <入力フォルダ> [-o 出力.csv]

処理の流れ（すべてローカルで完結し、ネットワークも外部 API も使わない）:
  1. PDF はテキスト層を PyMuPDF で読む。文字が無いページ（スキャン画像）は画像化して OCR に回す
  2. 画像（.png/.jpg/.jpeg）とスキャンページは macOS 標準の Vision フレームワークで OCR する
     （swift で小さなヘルパーを動かす。倍率と言語補正を変えて 3 回読み、項目ごとに多数決する）
  3. 文字の位置から見た目どおりの行を組み立て、書式とキーワードのルールで
     日付・支払った合計金額・店名を取り出す
読めないファイルや取れなかった項目は空欄にして、処理は止めない。
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import traceback
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

EXTENSIONS = (".pdf", ".png", ".jpg", ".jpeg")
HEADER = ["file", "date", "amount", "store"]
FIELDS = ("date", "amount", "store")

MAX_PDF_PAGES = 20      # 1 つの PDF で読む最大ページ数
MAX_OCR_PAGES = 5       # 1 つの PDF で OCR する最大ページ数
OCR_TARGET_PX = 1600    # 小さい画像は長辺がこのくらいになるまで拡大してから OCR する
OCR_MAX_PX = 4096       # OCR に渡す画像の長辺の上限

TODAY = dt.date.today()


def warn(msg: str) -> None:
    print(f"警告: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# 文字列の正規化
# ---------------------------------------------------------------------------

_DASHES = dict.fromkeys(map(ord, "‐‑‒–—―−﹣"), "-")


def norm_text(s: str) -> str:
    """全角英数・半角カナ・記号のゆれを揃える（NFKC）。"""
    s = unicodedata.normalize("NFKC", s).translate(_DASHES)
    s = re.sub(r"(?<=\d)\s*[ーｰ一]\s*(?=\d)", "-", s)  # OCR が数字の間の - を長音や「一」と読むことがある
    s = re.sub(r"(?<=\d)[Oo](?=[\d,])|(?<=[\d,])[Oo](?=\d)", "0", s)  # OCR の O と 0 の取り違え
    s = re.sub(r"\\(?=\s*\d)", "¥", s)                 # 日本語フォントの \ は円記号
    s = re.sub(r"(?<![A-Za-z])Y(?=\s?\d{1,3}(?:,\d{3})+(?!\d))", "¥", s)  # OCR が ¥ を Y と読むことがある
    return re.sub(r"\s+", " ", s).strip()


def compact(s: str) -> str:
    """空白を除いた形（「合　計」のような字間空けに対応するため）。

    英数字どうしの間の空白だけは残す（「HOTEL」の中の tel のような誤一致を単語の境目で防ぐため）。
    """
    return re.sub(r"(?<![A-Za-z0-9])\s+|\s+(?![A-Za-z0-9])", "", s)


def has_letter(s: str) -> bool:
    return re.search(r"[^\W\d_]", s) is not None


# ---------------------------------------------------------------------------
# レイアウト: 文字のまとまり（Segment）から見た目どおりの行（Row）を作る
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    """文字のまとまり 1 つ（PDF の 1 行、OCR の認識結果 1 つ）。

    pts は文字の向きで見た 左上・右上・右下・左下 の 4 点（画像座標、y は下向き）。
    """
    text: str
    pts: list
    size: float = 0.0  # 文字サイズ（PDF のみ。0 なら形から求める）


@dataclass
class Row:
    text: str     # 正規化済みの 1 行
    size: float   # 文字の大きさ（店名の推定に使う）


def build_rows(segments: list[Segment]) -> list[Row]:
    segs = [s for s in segments if s.text and s.text.strip()]
    if not segs:
        return []
    # 画像が 90 度回転・傾いていても行を組めるよう、文字の進む向きの平均で座標を回して揃える
    vx = sum(s.pts[1][0] - s.pts[0][0] for s in segs)
    vy = sum(s.pts[1][1] - s.pts[0][1] for s in segs)
    theta = math.atan2(vy, vx) if (vx or vy) else 0.0
    cos_t, sin_t = math.cos(-theta), math.sin(-theta)

    items = []
    for s in segs:
        pts = [(x * cos_t - y * sin_t, x * sin_t + y * cos_t) for x, y in s.pts]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        top, bottom = min(ys), max(ys)
        items.append({"x": min(xs), "top": top, "bottom": bottom,
                      "size": s.size or (bottom - top), "text": s.text})

    # 縦方向に半分以上重なるまとまりを同じ行とみなす
    items.sort(key=lambda it: (it["top"] + it["bottom"]) / 2)
    groups: list[dict] = []
    for it in items:
        if groups:
            g = groups[-1]
            overlap = min(g["bottom"], it["bottom"]) - max(g["top"], it["top"])
            if overlap >= 0.5 * max(1e-6, min(g["bottom"] - g["top"], it["bottom"] - it["top"])):
                g["items"].append(it)
                n = len(g["items"])
                g["top"] += (it["top"] - g["top"]) / n
                g["bottom"] += (it["bottom"] - g["bottom"]) / n
                continue
        groups.append({"top": it["top"], "bottom": it["bottom"], "items": [it]})

    rows = []
    for g in groups:
        members = sorted(g["items"], key=lambda it: it["x"])
        text = norm_text(" ".join(m["text"] for m in members))
        if text:
            rows.append(Row(text, max(m["size"] for m in members)))
    return rows


def rows_from_text(text: str) -> list[Row]:
    """位置情報の無いテキスト（pdftotext の出力など）から行を作る。"""
    return [Row(t, 0.0) for t in (norm_text(line) for line in text.splitlines()) if t]


# ---------------------------------------------------------------------------
# 日付
# ---------------------------------------------------------------------------

ERA_START = {"令和": 2018, "平成": 1988, "昭和": 1925}
ERA_ALIAS = {"令和": "令和", "今和": "令和", "令": "令和", "和": "令和", "R": "令和",
             "平成": "平成", "成": "平成", "H": "平成", "昭和": "昭和", "S": "昭和"}
MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}

# 年月日の漢字がある形は、文字間が空いた「1 0 月」も拾う
_KANJI_MD = r"\s*年\s*(?P<m>\d(?:\s?\d)?)\s*月\s*(?P<d>\d(?:\s?\d)?)\s*日"
_SEP = r"\s*[/.\-]\s*"
_MON = r"(?<![a-z])(?P<mon>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"

# (種類, 基本点, 正規表現)
DATE_PATTERNS = [
    # 令和8年8月20日 / R8年… / OCR で「令」が欠けた「和8年…」
    ("era", 10, re.compile(r"(?P<era>令和|平成|昭和|今和|令|和|成|(?<![A-Za-z])[RHS])\s*(?P<y>元|\d(?:\s?\d)?)"
                           + _KANJI_MD + "?")),
    # R8.8.20 / 令和8/8/20
    ("era", 9, re.compile(r"(?P<era>令和|平成|昭和|(?<![A-Za-z])[RHS])\s*(?P<y>元|\d{1,2})"
                          + _SEP + r"(?P<m>\d{1,2})" + _SEP + r"(?P<d>\d{1,2})(?!\d)")),
    # 2026年9月3日
    ("ymd", 10, re.compile(r"(?<!\d)(?P<y>\d(?:\s?\d){3})" + _KANJI_MD + "?")),
    # 2026/09/14, 2026-10-01, 2026.10.05
    ("ymd", 10, re.compile(r"(?<!\d)(?P<y>\d{4})" + _SEP + r"(?P<m>\d{1,2})" + _SEP + r"(?P<d>\d{1,2})(?!\d)")),
    # 元号の無い「8年8月20日」
    ("short", 6, re.compile(r"(?<![\d年])(?P<y>\d(?:\s?\d)?)" + _KANJI_MD)),
    # Oct 5, 2026 / 5 Oct 2026
    ("en", 8, re.compile(_MON + r"\s*(?P<d>\d{1,2})(?:st|nd|rd|th)?,?\s*(?P<y>\d{4})(?!\d)", re.I)),
    ("en", 8, re.compile(r"(?<!\d)(?P<d>\d{1,2})(?:st|nd|rd|th)?\s*" + _MON + r",?\s*(?P<y>\d{4})(?!\d)", re.I)),
    # 26/10/05（年が 2 桁）
    ("yy", 3, re.compile(r"(?<![\d/.\-])(?P<y>\d{2})[/.](?P<m>\d{1,2})[/.](?P<d>\d{1,2})(?![\d/.\-])")),
    # 10/05/2026（月/日/年）
    ("mdy", 4, re.compile(r"(?<![\d/])(?P<m>\d{1,2})/(?P<d>\d{1,2})/(?P<y>\d{4})(?!\d)")),
]

DATE_GOOD = re.compile(r"日付|発行|領収日|取引日|利用日|乗車日|降車日|購入日|買上日|買い上げ日|受付日|精算|出庫|"
                       r"支払日|決済日|売上日|計上日|退室|チェックアウト|日時|年月日|(?<![a-z])date(?![a-z])", re.I)
DATE_BAD = re.compile(r"期限|有効|迄|まで|生年月日|誕生|入庫|入場|入室|チェックイン|予約|次回|開始|発送|お届け|配達|"
                      r"交付|登録|契約|印刷|出力|再発行|入会|締切|保証|賞味|満了|更新|スキャン|valid|expir|"
                      r"(?<![a-z])due(?![a-z])|birth|scan|print|generat", re.I)
RANGE_AFTER_RE = re.compile(r"\s*(?:\([^)]{1,3}\))?\s*(?:[~〜]|-(?!\d{1,2}:)|から)")  # 「10月10日~」= 期間の始まり


def _num(s: str) -> int:
    return int(re.sub(r"\s", "", s))


def _resolve_year(kind: str, m: re.Match) -> int | None:
    y = m.group("y")
    if kind == "era":
        era = ERA_ALIAS[m.group("era")]
        return ERA_START[era] + (1 if y == "元" else _num(y))
    if kind == "short":
        # 元号が読めなかった 2 桁の年: 令和・西暦下 2 桁・平成のうち、未来でなく今に一番近いもの
        n = _num(y)
        options = [2018 + n, 2000 + n] + ([1988 + n] if n <= 31 else [])
        options = [o for o in options if 1989 <= o <= TODAY.year + 1]
        return min(options, key=lambda o: abs(TODAY.year - o)) if options else None
    if kind == "yy":
        return 2000 + int(y)
    return _num(y)


def _make_date(kind: str, m: re.Match) -> dt.date | None:
    year = _resolve_year(kind, m)
    month = MONTHS[m.group("mon").lower()[:3]] if kind == "en" else _num(m.group("m"))
    try:
        d = dt.date(year, month, _num(m.group("d")))
    except (TypeError, ValueError):
        return None
    if not (1989 <= d.year <= TODAY.year + 10):
        return None
    return d


YEAR_NOTE_RE = re.compile(r"\s*\((?:令和|平成|昭和|[RHS])?\s*(?:元|\d{1,4})\s*年?\)")


def date_matches(text: str) -> list[tuple[int, int, dt.date, int]]:
    """行の中の日付をすべて返す: (開始, 終了, 日付, 基本点)。位置は text 基準。"""
    # 「2026年(令和8年)10月1日」のような年の併記は、同じ長さの空白に置き換えてから探す
    text = YEAR_NOTE_RE.sub(lambda m: " " * len(m.group()), text)
    found = []
    for kind, base, rx in DATE_PATTERNS:
        for m in rx.finditer(text):
            d = _make_date(kind, m)
            if d:
                found.append((m.start(), m.end(), d, base))
    return found


def find_date(rows: list[Row]) -> str:
    best = None
    for ri, row in enumerate(rows):
        matches = date_matches(row.text)
        for start, end, d, base in matches:
            # この日付の見出し = 同じ行で直前の日付より後ろ、この日付より前の文字
            left = max([e for s, e, _, _ in matches if e <= start], default=0)
            label = compact(row.text[left:start])
            if not has_letter(label) and ri > 0 and not date_matches(rows[ri - 1].text):
                label = compact(rows[ri - 1].text)[-12:]  # 見出しだけ前の行にあるとき
            score = base
            if DATE_BAD.search(label):
                score -= 6
            elif DATE_GOOD.search(label):
                score += 5
            if RANGE_AFTER_RE.match(row.text, end):  # 宿泊・利用期間の始まりの日付は発行日ではないことが多い
                score -= 3
            if d > TODAY + dt.timedelta(days=31):
                score -= 3
            key = (score, -ri, -start)
            if best is None or key > best[0]:
                best = (key, d)
    return best[1].isoformat() if best else ""


# ---------------------------------------------------------------------------
# 金額
# ---------------------------------------------------------------------------

MONEY_RE = re.compile(r"""
    (?P<neg>(?<![-.・…])[-▲△]\s?)?   # 「合計-----¥1,280」の点線は負号にしない
    (?P<pre>[¥\\]\s?|JPY\s?)?
    (?P<num>\d{1,3}(?:[,.]\s?\d{3})+(?![\d,])|\d+)
    (?P<dec>\.\d{1,2}(?!\d))?
    (?P<suf>\s?円|\s?-(?![\d-])|\s?JPY)?
""", re.X | re.I)

# 金額と紛らわしい数字（時刻・電話・登録番号・税率など）は先に消しておく
NOISE_RES = [
    re.compile(r"(?<!\d)\d{1,2}:\d{2}(?::\d{2})?(?!\d)"),
    re.compile(r"\(?0\d{1,4}\)?[-\s]?\d{1,4}-\d{3,4}(?!\d)"),
    re.compile(r"T\s?\d{13}"),
    re.compile(r"\d+(?:\.\d+)?\s?%"),
    re.compile(r"〒\s?\d{3}-?\d{4}|(?<!\d)\d{3}-\d{4}(?!\d)"),
    re.compile(r"(?:No|NO|no|№|#)\.?\s?\d+"),
    re.compile(r"[x×@]\s?\d+(?:,\d{3})*"),
]
UNIT_AFTER = re.compile(r"\s?(?:点|個|品|枚|本|冊|名|人|件|回|分|秒|時間|泊|日|ヶ月|か月|ヵ月|月|年|号|番|階|歳|才|"
                        r"行|台|部|式|箱|袋|杯|皿|食|席|室|錠|包|km|kg|cm|mm|ml|pt|ポイント|%|g\b|m\b|l\b|p\b)",
                        re.I)

SUBTOTAL_RE = re.compile(r"小計|小合計|(?<![a-z])sub[- ]?total", re.I)
TENDERED_RE = re.compile(r"預|tendered", re.I)
CHANGE_RE = re.compile(r"お釣|釣銭|釣り?銭|おつり|^釣|釣$|(?<![a-z])change(?![a-z])", re.I)
TAX_RE = re.compile(r"消費税|外税|内税|税額|税等|うち税|(?<![a-z])tax(?:es)?(?![a-z])", re.I)
INNER_TAX_RE = re.compile(r"内|うち|込|incl|^\(", re.I)  # 「(消費税等 ¥116)」の括弧書きも内税
EXCLUDE_RE = re.compile(r"対象|税抜|税別|本体|値引(?!後)|割引(?!後)|引き|クーポン|ポイント|単価|数量|点数|個数|"
                        r"返金|返品|残高|残額|前回|累計|入金|チャージ|内訳|番号|コード|"
                        r"(?<![a-z])(?:discount|points?|balance)(?![a-z])",
                        re.I)
P1_RE = re.compile(r"支払|請求|領収金額|領収額|会計|税込合計|総合計|総額|利用金額|利用額|決済金額|決済額|精算金額|"
                   r"amount ?paid|grand ?total|total ?amount|total ?paid|amount ?due|total ?due", re.I)
# 「お買上計」は値引き前のことがあるので合計扱い（後に出てくる合計を優先する）
P2_RE = re.compile(r"合計|総計|台計|^計$|金額|税込|買上|買い上げ|(?<![a-z])total(?![a-z])", re.I)
P3_RE = re.compile(r"料金|運賃|代金|クレジット|カード|電子マネー|交通系|(?<![a-z])(?:qr|paypay|suica|pasmo|quicpay|"
                   r"nanaco|waon|edy|credit(?: ?card)?|card|visa|master(?:card)?|jcb|amex)(?![a-z])", re.I)
CASH_RE = re.compile(r"現金|(?<![a-z])cash(?![a-z])", re.I)


@dataclass
class Money:
    value: int
    strength: int          # 3: ¥/円つき, 2: 3 桁区切り or 「-」止め, 1: ただの数字
    negative: bool
    start: int
    end: int
    label: str | None = None


def money_tokens(text: str) -> list[Money]:
    cleaned = text
    for rx in NOISE_RES + [p for _, _, p in DATE_PATTERNS]:
        cleaned = rx.sub(lambda m: " " * len(m.group()), cleaned)
    tokens = []
    for m in MONEY_RE.finditer(cleaned):
        num = m.group("num")
        suffix = (m.group("suf") or "").strip()
        has_yen = bool(m.group("pre")) or suffix in ("円", "JPY", "jpy")
        if not has_yen:
            prev = cleaned[m.start() - 1] if m.start() > 0 else ""
            if prev.isascii() and prev.isalpha():
                continue  # USB3 など
            if UNIT_AFTER.match(cleaned, m.end()):
                continue  # 1点・3個・10% など
        value = int(re.sub(r"\D", "", num))
        if value > 99_999_999:
            continue
        grouped = re.search(r"[,.]\s?\d{3}", num) is not None
        strength = 3 if has_yen else 2 if (grouped or suffix == "-") else 1
        tokens.append(Money(value, strength, bool(m.group("neg")), m.start(), m.end()))
    if any(t.strength >= 2 for t in tokens):
        tokens = [t for t in tokens if t.strength >= 2]  # ¥ つきの金額がある行のただの数字は個数などとみなす
    # 金額ごとの見出し = 直前の金額からこの金額までの文字。記号だけなら直前の見出しを引き継ぐ
    prev_end, prev_label = 0, None
    for t in tokens:
        label = compact(text[prev_end:t.start])
        t.label = label if has_letter(label) else prev_label
        prev_end, prev_label = t.end, t.label
    return tokens


def classify(label: str) -> str:
    # 「お買上点数 3点 合計」のように数字を挟んで語が並ぶときは、金額に一番近い語で判断する
    parts = [p for p in re.split(r"\d[\d,.]*\s*(?:点|個|品|枚|本|冊|件|名|%)?", label) if has_letter(p)]
    if parts and parts[-1] != label:
        near = _classify(parts[-1])
        if near != "none":
            return near
    return _classify(label)


def _classify(label: str) -> str:
    if SUBTOTAL_RE.search(label):
        return "subtotal"
    if TENDERED_RE.search(label):
        return "tendered"
    if CHANGE_RE.search(label):
        return "change"
    if EXCLUDE_RE.search(label):
        return "exclude"
    if TAX_RE.search(label) and not re.search(r"total.*incl|税込", label, re.I):
        return "exclude" if INNER_TAX_RE.search(label) else "tax"
    if P1_RE.search(label):
        return "cash" if CASH_RE.search(label) else "P1"
    if P2_RE.search(label):
        return "P2"
    if P3_RE.search(label):
        return "P3"
    if CASH_RE.search(label):
        return "cash"
    return "none"


def find_amount(rows: list[Row]) -> str:
    groups: dict[str, list[Money]] = {}
    pending = None  # 金額の無い見出しだけの行（次の行の金額に引き継ぐ）
    for row in rows:
        tokens = money_tokens(row.text)
        if not tokens:
            c = compact(row.text)
            pending = c if (has_letter(c) and len(c) <= 24) else None
            continue
        for t in tokens:
            if t.label is None:
                t.label = pending or ""
        pending = None
        for t in tokens:
            if not t.negative:
                groups.setdefault(classify(t.label), []).append(t)

    def pick(cls: str, how: str = "last") -> int | None:
        toks = [t for t in groups.get(cls, []) if t.value > 0]
        if not toks:
            return None
        best = max(t.strength for t in toks)
        toks = [t for t in toks if t.strength == best]
        return toks[-1].value if how == "last" else max(t.value for t in toks)

    def last_any(cls: str) -> int | None:
        toks = groups.get(cls, [])
        return toks[-1].value if toks else None

    # 優先順: 支払・請求額 → 合計 → お預り-お釣り → 料金/カード払い → 現金 → 小計(+外税) → お預り → 一番大きい¥金額
    for cls in ("P1", "P2"):
        v = pick(cls)
        if v:
            return str(v)
    paid, change = pick("tendered") or pick("cash"), last_any("change")
    if paid is not None and change is not None and paid > change:
        return str(paid - change)
    v = pick("P3", "max")
    if v:
        return str(v)
    if change is None and pick("cash"):
        return str(pick("cash"))
    subtotal = pick("subtotal")
    if subtotal:
        return str(subtotal + (pick("tax") or 0))
    if pick("tendered"):
        return str(pick("tendered"))
    toks = [t for t in groups.get("none", []) if t.strength >= 2 and t.value > 0]
    if toks:
        best = max(t.strength for t in toks)
        return str(max(t.value for t in toks if t.strength == best))
    return ""


# ---------------------------------------------------------------------------
# 店名
# ---------------------------------------------------------------------------

STORE_LABEL_RE = re.compile(
    r"^(?:(?:店名|店舗名|店舗|販売店|発行元|発行者|事業者名|事業者|会社名|加盟店名|加盟店)\s*[:：]?"
    r"|(?:store|shop|merchant)(?:\s*name)?\s*[:：])\s*(?P<v>\S.*)$", re.I)
NOT_STORE_RES = [
    re.compile(r"(?<![a-z])(?:tel|fax)(?![a-z])|電話|☎|℡|フリーダイヤル|\d{2,4}-\d{2,4}-\d{3,4}", re.I),
    re.compile(r"〒|\d{3}-\d{4}|^(?:東京都|北海道|大阪府|京都府|\w{2,3}県)\S*?[市区町村郡].*\d|"
               r"[市区町村郡].*\d+-\d+|丁目\s*\d|"
               r"\d+番地?\s*\d*号?$|\d+-\d+-\d+"),
    re.compile(r"登録番号|事業者番号|インボイス|T\d{13}"),
    re.compile(r"https?://|www\.|\.(?:com|jp|net|org)\b|@", re.I),
    re.compile(r"領収|レシート|receipt|請求書|納品書|見積|明細|控|再発行|売上票|計算書|精算書|証明書|会計票|"
               r"利用票|受領書|invoice", re.I),
    re.compile(r"ありがと|いらっしゃいませ|ご来店|またの|毎度|お待ち|上記|正に|但し|として|問い?合わ?せ|"
               r"営業時間|定休日|返品|交換|保管|お客様|ご利用|thank|welcome", re.I),
    re.compile(r"ポイント|会員|番号|承認|伝票|担当|レジ(?:[#№:\d]|$|No)|取引|端末|責任者|No\.|#\d", re.I),
    re.compile(r"合計|小計|金額|料金|運賃|お釣|釣銭|釣り銭|おつり|お預|預り|預かり|消費税|内税|外税|税込|税抜|"
               r"税額|税率|対象|点数|数量|単価|値引|割引|支払|請求|現金|クレジット|(?<![a-z])(?:sub ?)?total(?![a-z])", re.I),
    re.compile(r"(?:様|御中|殿)$"),
    re.compile(r"[x×@]\s?\d|\d\s?(?:点|個|枚|時間|分|秒|泊|名|人)"),  # 品目・数量・時間の行
    re.compile(r"^(?:日付|発行日|乗車日|利用日|入庫|出庫|日時|時刻)|^(?:date|time)(?:\s*[:：]|\s*\d|$)", re.I),
    re.compile(r"(?<!\d)\d{1,2}:\d{2}"),
]
STORE_WORD_RE = re.compile(
    r"店|堂|屋|舗|商店|書店|書房|株式会社|\(株\)|有限会社|\(有\)|合同会社|交通|タクシー|電器|電機|電気|薬局|"
    r"ドラッグ|食堂|処|亭|庵|軒|館|ホテル|旅館|駐車場|パーキング|parking|store|shop|cafe|coffee|restaurant|"
    r"bakery|market|mart|マート|ストア|ショップ|カフェ|珈琲|喫茶|クリニック|医院|病院|歯科|ベーカリー|酒場|"
    r"居酒屋|寿司|鮨|そば|蕎麦|うどん|ラーメン|焼肉|商事|工業|センター|百貨店|スーパー|文具|印刷|鉄道|バス|"
    r"航空|石油|inc|llc|ltd|co\.|corp", re.I)
ISSUER_MARKER_RE = re.compile(r"上記.*領収|正に領収|領収いたしました|領収しました")
CORP_ONLY_RE = re.compile(r"株式会社|有限会社|合同会社|合資会社|\(株\)|\(有\)|一般社団法人|医療法人(?:社団)?")


def clean_store(s: str) -> str:
    s = norm_text(s).strip(" *=~・･◆◇■□●○★☆◎|_:;.,、。-")
    s = re.sub(r"[(\[【「『《<]+$|^[)\]】」』》>]+", "", s).strip()  # 切り離しで残った片側だけの括弧
    m = re.fullmatch(r"[【\[<《『「(]([^【\[<《『「()\]>》』」】]+)[】\]>》』」)]", s)  # 全体を囲む括弧だけ外す
    if m:
        s = m.group(1).strip()
    return re.sub(r"\s+", " ", s)


def looks_like_store(text: str) -> bool:
    c = compact(text)
    letters = sum(1 for ch in c if has_letter(ch))
    if letters < 2 or len(c) > 40 or letters < len(c) * 0.5:
        return False
    if date_matches(text):
        return False
    # 「ブレンド ¥550」「合計 3,160円」のような金額の行は除く（「100円ショップ」のように頭にあるものは残す）
    if any(t.strength == 3 and (text[t.start:t.end].lstrip().startswith(("¥", "\\", "JPY"))
                                or t.end >= len(text.rstrip()) - 1) for t in money_tokens(text)):
        return False
    return not any(rx.search(c) for rx in NOT_STORE_RES)


def find_store(rows: list[Row]) -> str:
    sizes = sorted(r.size for r in rows if r.size > 0)
    median = sizes[len(sizes) // 2] if sizes else 0.0
    best = None
    rank = 0
    after_issuer = False
    for i, row in enumerate(rows):
        m = STORE_LABEL_RE.match(row.text)
        text = m.group("v") if m else row.text
        # 「カフェ ミドリ堂 TEL 03-…」「… No.0012」のように同じ行に続く連絡先・番号は切り離す
        text = re.split(r"\s*[(\[【]?\s*(?:TEL|Tel|tel|電話|☎|℡|FAX|Fax|No\.|NO\.|№|#)\s*[:：.]?\s*(?=[\d(])",
                        text)[0]
        if (m and has_letter(text)) or looks_like_store(text):
            score = 10.0 if m else 0.0
            score += max(0, 3 - rank)                     # 上の方の行ほど店名らしい
            if median and row.size >= median * 1.15:     # 大きな文字
                score += 3
            if STORE_WORD_RE.search(compact(text)):       # 店・堂・屋・株式会社 など
                score += 2
            if after_issuer:                              # 「上記正に領収いたしました」の後ろは発行者
                score += 3
            rank += 1
            if best is None or score > best[0]:
                best = (score, text, i)
        if ISSUER_MARKER_RE.search(compact(row.text)):
            after_issuer = True
    if not best:
        return ""
    text, i = best[1], best[2]
    # 「株式会社」だけの行は、次の行の社名とつなげる
    if CORP_ONLY_RE.fullmatch(compact(text)) and i + 1 < len(rows) and looks_like_store(rows[i + 1].text):
        text = text + " " + rows[i + 1].text
    return clean_store(text)


def extract_fields(rows: list[Row]) -> dict[str, str]:
    return {"date": find_date(rows), "amount": find_amount(rows), "store": find_store(rows)}


def vote(results: list[dict[str, str]]) -> dict[str, str]:
    """OCR を設定違いで読んだ結果を項目ごとに多数決する。同数なら得意な設定の結果を採る。"""
    prefer = {"date": (1, 0, 2), "amount": (1, 0, 2), "store": (0, 2, 1)}  # 1: 言語補正なし（数字に強い）
    out = {}
    for f in FIELDS:
        values = [r.get(f, "") for r in results]
        keys = [re.sub(r"\s+", "", v) for v in values]
        counts = Counter(k for k in keys if k)
        if not counts:
            out[f] = ""
            continue
        top = max(counts.values())
        order = [i for i in prefer[f] if i < len(values)] + [i for i in range(len(values)) if i not in prefer[f]]
        out[f] = next(values[i] for i in order if keys[i] and counts[keys[i]] == top)
    return out


# ---------------------------------------------------------------------------
# OCR（macOS Vision を swift から呼ぶ）
# ---------------------------------------------------------------------------

SWIFT_SOURCE = r"""
import Foundation
import Vision
import ImageIO
import CoreGraphics

// 標準入力: 1 行に「画像パス<TAB>倍率:言語補正(1/0),倍率:言語補正,...」
// 標準出力: 画像×設定ごとに JSON 1 行 {"i":番号,"p":設定番号,"lines":[{"t":文字,"c":確信度,"q":[4 点の座標]}]}

func emit(_ obj: [String: Any]) {
    if let data = try? JSONSerialization.data(withJSONObject: obj, options: []),
       let s = String(data: data, encoding: .utf8) {
        print(s)
        fflush(stdout)
    }
}

func loadImage(_ path: String) -> CGImage? {
    guard let src = CGImageSourceCreateWithURL(URL(fileURLWithPath: path) as CFURL, nil) else { return nil }
    return CGImageSourceCreateImageAtIndex(src, 0, nil)
}

func scaled(_ img: CGImage, _ s: Double) -> CGImage? {
    let w = max(1, Int((Double(img.width) * s).rounded()))
    let h = max(1, Int((Double(img.height) * s).rounded()))
    guard let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0,
                              space: CGColorSpaceCreateDeviceRGB(),
                              bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { return nil }
    ctx.setFillColor(CGColor(red: 1, green: 1, blue: 1, alpha: 1))
    ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
    ctx.interpolationQuality = .high
    ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
    return ctx.makeImage()
}

func recognize(_ img: CGImage, corr: Bool) throws -> [[String: Any]] {
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.usesLanguageCorrection = corr
    req.minimumTextHeight = 0
    let wanted = ["ja-JP", "en-US"]
    if let supported = try? req.supportedRecognitionLanguages() {
        req.recognitionLanguages = wanted.filter { supported.contains($0) }
    } else {
        req.recognitionLanguages = wanted
    }
    try VNImageRequestHandler(cgImage: img, options: [:]).perform([req])
    let W = Double(img.width), H = Double(img.height)
    func pt(_ p: CGPoint) -> [Double] { [Double(p.x) * W, (1.0 - Double(p.y)) * H] }
    var lines: [[String: Any]] = []
    for obs in req.results ?? [] {
        guard let cand = obs.topCandidates(1).first else { continue }
        lines.append(["t": cand.string, "c": Double(cand.confidence),
                      "q": pt(obs.topLeft) + pt(obs.topRight) + pt(obs.bottomRight) + pt(obs.bottomLeft)])
    }
    return lines
}

var index = 0
while let line = readLine() {
    let parts = line.components(separatedBy: "\t")
    let specs = parts.count > 1 ? parts[1] : "1:1"
    autoreleasepool {
        guard let img = loadImage(parts[0]) else {
            emit(["i": index, "error": "cannot load image"])
            return
        }
        for (k, spec) in specs.split(separator: ",").enumerated() {
            let f = spec.split(separator: ":")
            let s = Double(f.first ?? "1") ?? 1.0
            let corr = f.count > 1 ? f[1] == "1" : true
            guard let im = abs(s - 1.0) < 0.001 ? img : scaled(img, s) else {
                emit(["i": index, "p": k, "error": "cannot scale image"])
                continue
            }
            do {
                emit(["i": index, "p": k, "lines": try recognize(im, corr: corr)])
            } catch {
                emit(["i": index, "p": k, "error": "\(error)"])
            }
        }
    }
    index += 1
}
"""


def ocr_passes(width: int, height: int) -> list[tuple[float, bool]]:
    """OCR の読み方 3 通り: (倍率, 言語補正)。小さい画像ほど拡大し、倍率と補正の有無を変えて読む。"""
    longest = max(width, height, 1)
    base = min(4.0, max(1.0, OCR_TARGET_PX / longest))
    alt = base * 1.5 if longest * base * 1.5 <= OCR_MAX_PX else base * 0.7
    return [(base, True), (base, False), (alt, True)]


def run_vision(jobs: list[tuple[str, list[tuple[float, bool]]]], workdir: str,
               debug: bool = False) -> dict[int, dict[int, list[Segment]]]:
    """画像をまとめて OCR する。戻り値は {ジョブ番号: {設定番号: [Segment]}}。"""
    if not jobs:
        return {}
    swift = shutil.which("swift")
    if swift is None:
        warn("swift コマンドが見つからないため、画像の文字認識（OCR）をスキップします"
             "（Xcode Command Line Tools が必要です）")
        return {}
    script = os.path.join(workdir, "vision_ocr.swift")
    with open(script, "w", encoding="utf-8") as f:
        f.write(SWIFT_SOURCE)
    request = "".join(
        path + "\t" + ",".join(f"{s:.3f}:{1 if c else 0}" for s, c in passes) + "\n"
        for path, passes in jobs).encode("utf-8")

    # 普段は swift でそのまま実行する。失敗したら一時フォルダをキャッシュにして再実行、最後は swiftc でビルドして実行
    cache = os.path.join(workdir, "swift-module-cache")
    binary = os.path.join(workdir, "vision_ocr")
    attempts = [(None, [swift, script]), (None, [swift, "-module-cache-path", cache, script])]
    swiftc = shutil.which("swiftc")
    if swiftc:
        attempts.append(([swiftc, "-O", "-module-cache-path", cache, "-o", binary, script], [binary]))
    err = b""
    for build, cmd in attempts:
        try:
            if build:
                built = subprocess.run(build, capture_output=True, timeout=300)
                if built.returncode != 0:
                    err = built.stderr
                    continue
            proc = subprocess.run(cmd, input=request, capture_output=True, timeout=120 + 30 * len(jobs))
        except subprocess.TimeoutExpired as e:
            warn("OCR が時間内に終わらなかったため、途中までの結果を使います")
            return _parse_vision_output(e.stdout or b"")
        except OSError as e:
            err = str(e).encode()
            continue
        err = proc.stderr
        if debug and err:
            print(err.decode("utf-8", "replace"), file=sys.stderr)
        results = _parse_vision_output(proc.stdout)
        if results:
            return results
    detail = err.decode("utf-8", "replace").strip().splitlines()
    warn("画像の文字認識（OCR）に失敗しました" + (f": {detail[-1]}" if detail else ""))
    return {}


def _parse_vision_output(out: bytes) -> dict[int, dict[int, list[Segment]]]:
    results: dict[int, dict[int, list[Segment]]] = {}
    for line in out.decode("utf-8", "replace").splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if not isinstance(obj, dict) or "lines" not in obj:
            continue
        segs = []
        for item in obj["lines"]:
            q = item.get("q") or []
            if len(q) == 8:
                segs.append(Segment(item.get("t", ""), [(q[0], q[1]), (q[2], q[3]), (q[4], q[5]), (q[6], q[7])]))
        results.setdefault(obj["i"], {})[obj.get("p", 0)] = segs
    return results


# ---------------------------------------------------------------------------
# ファイルの読み込み
# ---------------------------------------------------------------------------

@dataclass
class Page:
    rows: list[Row] | None = None   # テキスト層から作った行（使えないときは None）
    job: int | None = None          # OCR ジョブ番号
    ocr_primary: bool = False       # True: OCR が主（スキャンページ）/ False: 取れなかった項目の補助


@dataclass
class Doc:
    name: str
    pages: list[Page] = field(default_factory=list)
    error: str | None = None


class OcrQueue:
    def __init__(self, workdir: str):
        self.workdir = workdir
        self.jobs: list[tuple[str, list[tuple[float, bool]]]] = []

    def add_png(self, save, width: int, height: int) -> int:
        path = os.path.join(self.workdir, f"ocr_{len(self.jobs):05d}.png")
        save(path)
        self.jobs.append((path, ocr_passes(width, height)))
        return len(self.jobs) - 1


def load_image(path: str, queue: OcrQueue) -> list[Page]:
    from PIL import Image, ImageOps

    with Image.open(path) as src:
        src.load()
        try:
            im = ImageOps.exif_transpose(src)  # スマホ写真の回転情報を反映
        except Exception:
            im = src.copy()
    if im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        im = Image.new("RGB", rgba.size, (255, 255, 255))  # 透明部分は白地にする
        im.paste(rgba, mask=rgba.getchannel("A"))
    elif im.mode != "RGB":
        im = im.convert("RGB")
    if max(im.size) > OCR_MAX_PX:
        im.thumbnail((OCR_MAX_PX, OCR_MAX_PX), Image.LANCZOS)
    job = queue.add_png(lambda p: im.save(p, "PNG"), im.width, im.height)
    return [Page(job=job, ocr_primary=True)]


def _quad(bbox, direction) -> list:
    """PDF の行の外接矩形と書字方向から 左上・右上・右下・左下 を作る（90 度単位）。"""
    x0, y0, x1, y1 = bbox
    dx, dy = direction
    if abs(dx) >= abs(dy):
        if dx >= 0:
            return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        return [(x1, y1), (x0, y1), (x0, y0), (x1, y0)]
    if dy < 0:
        return [(x0, y1), (x0, y0), (x1, y0), (x1, y1)]
    return [(x1, y0), (x1, y1), (x0, y1), (x0, y0)]


def _text_usable(segs: list[Segment]) -> bool:
    text = "".join(s.text for s in segs)
    meaningful = sum(ch.isalnum() for ch in text)
    broken = sum(1 for ch in text if ch == "\ufffd" or unicodedata.category(ch) in ("Co", "Cn"))
    return meaningful >= 6 and broken <= 0.2 * max(1, len(text))


def load_pdf(path: str, queue: OcrQueue) -> list[Page]:
    import fitz  # PyMuPDF

    try:
        doc = fitz.open(path, filetype="pdf")
    except Exception:
        return _load_pdf_with_pdftotext(path)
    with doc:
        if doc.needs_pass and not doc.authenticate(""):
            raise ValueError("パスワード付きの PDF のため読めません")
        pages, ocr_count = [], 0
        for pno in range(min(doc.page_count, MAX_PDF_PAGES)):
            try:
                page = doc[pno]
                segs = _pdf_segments(page)
                usable = _text_usable(segs)
                page_area = abs(page.rect) or 1
                big_image = any(abs(fitz.Rect(info["bbox"]) & page.rect) >= 0.1 * page_area
                                for info in page.get_image_info())
            except Exception:
                continue  # 壊れたページは飛ばして、残りのページで読む
            p = Page(rows=build_rows(segs) if usable else None, ocr_primary=not usable)
            if (not usable or big_image) and ocr_count < MAX_OCR_PAGES:
                try:
                    pix = _render_page(page)
                    p.job = queue.add_png(pix.save, pix.width, pix.height)
                    ocr_count += 1
                except Exception:
                    pass
            pages.append(p)
    return pages


def _pdf_segments(page) -> list[Segment]:
    segs = []
    for block in page.get_text("dict").get("blocks", []):
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = "".join(span.get("text", "") for span in spans)
            if not text.strip():
                continue
            main_span = max(spans, key=lambda sp: sp.get("size", 0))
            size = main_span.get("size", 0)
            x0, y0, x1, y1 = line["bbox"]
            dx, dy = line.get("dir", (1, 0))
            if size > 0 and dx > 0 and abs(dy) < 1e-3 and "origin" in main_span:
                # フォントによっては行の枠が大きく隣の行と重なるので、縦幅は文字サイズと基準線から決める
                base = main_span["origin"][1]
                y0, y1 = base - 0.8 * size, base + 0.2 * size
            segs.append(Segment(text, _quad((x0, y0, x1, y1), (dx, dy)), size))
    return segs


def _render_page(page):
    # 埋め込み画像の解像度に合わせて（150〜300dpi）画像化する
    dpi = 200.0
    effective = [info["width"] / ((info["bbox"][2] - info["bbox"][0]) / 72)
                 for info in page.get_image_info() if info["bbox"][2] - info["bbox"][0] > 1 and info.get("width")]
    if effective:
        dpi = max(150.0, min(300.0, max(effective)))
    longest = max(page.rect.width, page.rect.height, 1)
    dpi = max(36.0, min(dpi, OCR_MAX_PX * 72 / longest))
    return page.get_pixmap(dpi=int(dpi), alpha=False)


def _load_pdf_with_pdftotext(path: str) -> list[Page]:
    """PyMuPDF で開けない PDF は pdftotext でテキストだけ試す。"""
    exe = shutil.which("pdftotext")
    if exe:
        try:
            proc = subprocess.run([exe, "-layout", "-enc", "UTF-8", path, "-"], capture_output=True, timeout=60)
            text = proc.stdout.decode("utf-8", "replace")
            if proc.returncode == 0 and sum(ch.isalnum() for ch in text) >= 6:
                return [Page(rows=rows_from_text(text))]
        except (OSError, subprocess.SubprocessError):
            pass
    raise ValueError("PDF として開けません")


# ---------------------------------------------------------------------------
# 全体の処理
# ---------------------------------------------------------------------------

def list_receipts(folder: str) -> list[str]:
    names = []
    for name in os.listdir(folder):
        if name.lower().endswith(EXTENSIONS) and os.path.isfile(os.path.join(folder, name)):
            names.append(name)
    return sorted(names)


def doc_fields(doc: Doc, ocr: dict[int, dict[int, list[Segment]]], debug: bool = False) -> dict[str, str]:
    # 文字層が薄い（スキャン画像にスキャナーの透かし程度の文字しかない）ページは、画像の OCR を主に使う
    for p in doc.pages:
        if p.job is not None and not p.ocr_primary:
            text_chars = sum(ch.isalnum() for row in (p.rows or []) for ch in row.text)
            ocr_chars = max((sum(ch.isalnum() for seg in segs for ch in seg.text)
                             for segs in ocr.get(p.job, {}).values()), default=0)
            if ocr_chars > 2 * text_chars:
                p.ocr_primary = True
    jobs = [p.job for p in doc.pages if p.job is not None]
    n_pass = max((len(ocr.get(j, {})) for j in jobs), default=0)

    def page_rows(k: int | None, supplement: bool = False) -> list[Row]:
        rows: list[Row] = []
        for p in doc.pages:
            if supplement:
                if p.job is not None and not p.ocr_primary and k is not None:
                    rows += build_rows(ocr.get(p.job, {}).get(k, []))
            elif p.ocr_primary:
                if p.job is not None and k is not None:
                    rows += build_rows(ocr.get(p.job, {}).get(k, []))
            elif p.rows:
                rows += p.rows
        return rows

    def run(supplement: bool) -> dict[str, str]:
        uses_ocr = supplement or any(p.ocr_primary for p in doc.pages)
        passes = list(range(n_pass)) if (uses_ocr and n_pass) else [None]
        results = []
        for k in passes:
            rows = page_rows(k, supplement)
            results.append(extract_fields(rows))
            if debug:
                tag = "補助OCR" if supplement else ("OCR" if uses_ocr else "テキスト")
                print(f"--- {doc.name} [{tag} {k}] -> {results[-1]}", file=sys.stderr)
                for r in rows:
                    print(f"    {r.text}  (size={r.size:.1f})", file=sys.stderr)
        return vote(results) if len(results) > 1 else results[0]

    fields = run(supplement=False)
    if not all(fields.values()) and any(p.job is not None and not p.ocr_primary for p in doc.pages):
        extra = run(supplement=True)
        if not fields["date"] and not fields["amount"]:
            # テキスト層が領収書の中身ではない（透かしだけ等）とみなし、画像の OCR を優先する
            fields = {f: extra[f] or fields[f] for f in FIELDS}
        else:
            fields = {f: fields[f] or extra[f] for f in FIELDS}
    return fields


def process_folder(folder: str, debug: bool = False) -> list[list[str]]:
    names = list_receipts(folder)
    rows_out = []
    with tempfile.TemporaryDirectory(prefix="receipt2csv-") as workdir:
        queue = OcrQueue(workdir)
        docs = []
        for name in names:
            doc = Doc(name)
            path = os.path.join(folder, name)
            try:
                doc.pages = load_pdf(path, queue) if name.lower().endswith(".pdf") else load_image(path, queue)
            except Exception as e:  # 読めないファイルは空欄の行にして続ける
                doc.error = str(e) or type(e).__name__
                if debug:
                    traceback.print_exc()
            docs.append(doc)

        ocr = run_vision(queue.jobs, workdir, debug) if queue.jobs else {}

        for doc in docs:
            fields = {f: "" for f in FIELDS}
            if doc.error is None:
                try:
                    fields = doc_fields(doc, ocr, debug)
                except Exception as e:
                    doc.error = f"解析中のエラー: {e}"
                    if debug:
                        traceback.print_exc()
            if doc.error:
                warn(f"{doc.name}: 読み取れませんでした（{doc.error}）")
            else:
                missing = [label for f, label in zip(FIELDS, ("日付", "金額", "店名")) if not fields[f]]
                if missing:
                    warn(f"{doc.name}: {'・'.join(missing)}を取得できませんでした")
            rows_out.append([doc.name, fields["date"], fields["amount"], fields["store"]])
    return rows_out


def to_csv(rows: list[list[str]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(HEADER)
    writer.writerows(rows)
    return buf.getvalue()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="receipt2csv.py",
        description="フォルダ直下の領収書（.pdf .png .jpg .jpeg）から file,date,amount,store の CSV を作ります。",
    )
    parser.add_argument("folder", metavar="入力フォルダ", help="領収書ファイルが入ったフォルダ")
    parser.add_argument("-o", "--output", metavar="出力.csv", help="出力先の CSV（省略時は標準出力）")
    parser.add_argument("--debug", action="store_true", help="読み取った行と判定結果を標準エラーに出す")
    args = parser.parse_args(argv)

    if not os.path.exists(args.folder):
        print(f"エラー: 入力フォルダが見つかりません: {args.folder}", file=sys.stderr)
        return 2
    if not os.path.isdir(args.folder):
        print(f"エラー: 入力フォルダではありません（ファイルが指定されています）: {args.folder}", file=sys.stderr)
        return 2
    if args.output:
        out_dir = os.path.dirname(os.path.abspath(args.output))
        if os.path.isdir(args.output):
            print(f"エラー: 出力先がフォルダです: {args.output}", file=sys.stderr)
            return 2
        if not os.path.isdir(out_dir):
            print(f"エラー: 出力先のフォルダが見つかりません: {out_dir}", file=sys.stderr)
            return 2

    try:
        rows = process_folder(args.folder, debug=args.debug)
    except PermissionError as e:
        print(f"エラー: 入力フォルダを読めません: {e}", file=sys.stderr)
        return 1
    data = to_csv(rows)

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8", newline="") as f:
                f.write(data)
        except OSError as e:
            print(f"エラー: CSV を書き込めません: {e}", file=sys.stderr)
            return 1
        print(f"{len(rows)} 件を {args.output} に書き出しました", file=sys.stderr)
    else:
        sys.stdout.buffer.write(data.encode("utf-8"))
        sys.stdout.flush()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("中断しました", file=sys.stderr)
        sys.exit(130)

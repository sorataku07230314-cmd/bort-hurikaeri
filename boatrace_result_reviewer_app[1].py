# -*- coding: utf-8 -*-
"""
🎓 ぼーとだいがくせい｜レース結果×予想 答え合わせ＆敗因解剖アナライザー (Streamlit版)
========================================================================================
予想シミュレーターとは別サイトとして動作する「レース結果からの振り返り・検証・的中報告生成」専用アプリです。

【主な機能】
1. BOAT RACE公式の「レース結果(raceresult)」＋「直前情報(beforeinfo)」＋「出走表(racelist)」を自動取得！
   ・確定着順(1〜3着)、決まり手(逃げ/差し/まくり/まくり差し/抜き)、3連単配当、展示ST vs 本番実STを一括反映。
2. 事前の自分の予想（買い目・想定展開・投資金額）を入力すると、
   ・①展示STと本番実STのズレ（誰が踏み込み、誰がドカ遅れして壁が崩れたか）
   ・②1マークの決まり手と2・3着スジ連動の解剖
   ・③惜敗パターン診断（3着抜け・2着スジ抜け・裏目・展開逆行）
   ・④次レースに向けた「予想シミュレーター(PHASE 2 PRO)」の重み付けスライダー調整処方箋
   を自動算出！
3. X(@Boatrace__daisu) & note 用の「🎯的中報告ポスト」および「🔬1M展開答え合わせ検証ログ」をワンタップ出力。
"""

import datetime
import json
import os
import re
import subprocess
import sys
import unicodedata

try:
    from bs4 import BeautifulSoup
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry
except ModuleNotFoundError:
    _pkg_dir = "/tmp/boatrace_pkgs"
    os.makedirs(_pkg_dir, exist_ok=True)
    if _pkg_dir not in sys.path:
        sys.path.insert(0, _pkg_dir)
    try:
        from bs4 import BeautifulSoup
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry
    except ModuleNotFoundError:
        subprocess.check_call(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "--target",
                _pkg_dir,
                "--quiet",
                "beautifulsoup4",
                "requests",
                "urllib3",
            ]
        )
        from bs4 import BeautifulSoup
        import requests
        from requests.adapters import HTTPAdapter
        from urllib3.util.retry import Retry

import streamlit as st
import streamlit.components.v1 as components

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    )
}

VENUE_LIST = [
    ("01", "桐生"), ("02", "戸田"), ("03", "江戸川"), ("04", "平和島"),
    ("05", "多摩川"), ("06", "浜名湖"), ("07", "蒲郡"), ("08", "常滑"),
    ("09", "津"), ("10", "三国"), ("11", "びわこ"), ("12", "住之江"),
    ("13", "尼崎"), ("14", "鳴門"), ("15", "丸亀"), ("16", "児島"),
    ("17", "宮島"), ("18", "徳山"), ("19", "下関"), ("20", "若松"),
    ("21", "芦屋"), ("22", "福岡"), ("23", "唐津"), ("24", "大村"),
]


def make_official_session() -> requests.Session:
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        status=2,
        backoff_factor=0.4,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.headers.update(HEADERS)
    return session


def normalize_text(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").strip()


def fetch_official_result_bundle(hd: str, jcd: str, rno: int) -> dict:
    result_url = f"https://www.boatrace.jp/owpc/pc/race/raceresult?rno={rno}&jcd={jcd}&hd={hd}"
    before_url = f"https://www.boatrace.jp/owpc/pc/race/beforeinfo?rno={rno}&jcd={jcd}&hd={hd}"
    list_url = f"https://www.boatrace.jp/owpc/pc/race/racelist?rno={rno}&jcd={jcd}&hd={hd}"

    venue_name = dict(VENUE_LIST).get(jcd, "平和島")
    bundle = {
        "status": "ok",
        "venue": venue_name,
        "rno": rno,
        "grade": "G1",
        "fin1": 1,
        "fin2": 2,
        "fin3": 3,
        "kimarite": "nige",
        "payout": 1200,
        "windDir": "向かい風",
        "windSpeed": 3,
        "wave": 2,
        "boats": {
            str(b): {"id": b, "course": b, "name": f"{b}号艇", "exTime": 6.78, "preSt": 0.14, "actualSt": 0.14, "rank": b}
            for b in range(1, 7)
        },
    }

    try:
        session = make_official_session()

        # 1. 出走表から選手名・平均ST・グレード取得
        r_list = session.get(list_url, timeout=(5, 12))
        r_list.encoding = "utf-8"
        soup_list = BeautifulSoup(r_list.text, "html.parser")
        heading = soup_list.select_one("div.heading2_title")
        if heading:
            cls_str = " ".join(heading.get("class", []))
            if "is-sg" in cls_str:
                bundle["grade"] = "SG"
            elif "is-g1a" in cls_str:
                bundle["grade"] = "PG1"
            elif "is-g1b" in cls_str:
                bundle["grade"] = "G1"
            elif "is-g2" in cls_str:
                bundle["grade"] = "G2"
            elif "is-g3" in cls_str:
                bundle["grade"] = "G3"
            else:
                bundle["grade"] = "一般"

        tbodies = [
            tb for tb in soup_list.select("div.table1 table tbody")
            if re.search(r"\d{4}\s*/\s*(?:A1|A2|B1|B2)", tb.get_text())
        ]
        for idx, tb in enumerate(tbodies[:6]):
            b_no = idx + 1
            name_tag = tb.select_one("div.is-fs18")
            if name_tag:
                nm = re.sub(r"[\s\u3000]+", " ", name_tag.get_text(" ", strip=True)).strip()
                if nm:
                    bundle["boats"][str(b_no)]["name"] = nm

        # 2. 直前情報から展示タイム・展示ST取得
        try:
            r_bef = session.get(before_url, timeout=(4, 10))
            r_bef.encoding = "utf-8"
            soup_bef = BeautifulSoup(r_bef.text, "html.parser")
            for tb in soup_bef.select("div.table1 table tbody.is-fs12"):
                first_row = tb.find("tr")
                if not first_row:
                    continue
                cells = first_row.find_all("td", recursive=False)
                if len(cells) >= 5:
                    b_key = normalize_text(cells[0].get_text(strip=True))
                    ex_m = re.search(r"[67]\.\d{2}", normalize_text(cells[4].get_text(strip=True)))
                    if b_key in bundle["boats"] and ex_m:
                        bundle["boats"][b_key]["exTime"] = float(ex_m.group(0))
            for box in soup_bef.select("div.table1_boatImage1"):
                n_el = box.select_one(".table1_boatImage1Number")
                t_el = box.select_one(".table1_boatImage1Time")
                if n_el and t_el:
                    b_str = normalize_text(n_el.get_text(strip=True))
                    raw_t = normalize_text(t_el.get_text(strip=True)).replace("F", "").replace("L", "")
                    if b_str in bundle["boats"] and re.fullmatch(r"\.?\d{2}", raw_t):
                        bundle["boats"][b_str]["preSt"] = float("0" + raw_t) if raw_t.startswith(".") else float(raw_t)
        except Exception:
            pass

        # 3. レース結果ページから着順・決まり手・実ST・3連単配当を取得
        r_res = session.get(result_url, timeout=(5, 12))
        r_res.encoding = "utf-8"
        soup_res = BeautifulSoup(r_res.text, "html.parser")
        res_text = normalize_text(soup_res.get_text(" ", strip=True))

        if "データがありません" in res_text:
            return {"status": "error", "message": f"{hd} {venue_name} {rno}R のレース結果はまだ確定していません。"}

        # 着順テーブル解析
        order_list = []
        for tr in soup_res.select("div.table1 table tbody tr"):
            tds = [normalize_text(td.get_text(" ", strip=True)) for td in tr.find_all("td")]
            if len(tds) >= 4 and re.fullmatch(r"[1-6]", tds[0]) and re.fullmatch(r"[1-6]", tds[1]):
                rk = int(tds[0])
                bno = int(tds[1])
                order_list.append((rk, bno))
                bundle["boats"][str(bno)]["rank"] = rk

        order_list.sort(key=lambda x: x[0])
        if len(order_list) >= 3:
            bundle["fin1"] = order_list[0][1]
            bundle["fin2"] = order_list[1][1]
            bundle["fin3"] = order_list[2][1]

        # 本番スリットST解析
        for idx, box in enumerate(soup_res.select("div.table1_boatImage1"), start=1):
            n_el = box.select_one(".table1_boatImage1Number")
            t_el = box.select_one(".table1_boatImage1Time")
            if n_el:
                b_str = normalize_text(n_el.get_text(strip=True))
                if b_str in bundle["boats"]:
                    bundle["boats"][b_str]["course"] = idx
                    if t_el:
                        st_m = re.search(r"0?\.\d{2}", normalize_text(t_el.get_text(" ", strip=True)))
                        if st_m:
                            val_str = st_m.group(0)
                            bundle["boats"][b_str]["actualSt"] = float("0" + val_str) if val_str.startswith(".") else float(val_str)

        # 決まり手解析
        if "まくり差し" in res_text:
            bundle["kimarite"] = "makurisashi"
        elif "まくり" in res_text:
            bundle["kimarite"] = "makuri"
        elif "差し" in res_text:
            bundle["kimarite"] = "sashi"
        elif "抜き" in res_text:
            bundle["kimarite"] = "nuki"
        elif "恵まれ" in res_text:
            bundle["kimarite"] = "megumare"
        else:
            bundle["kimarite"] = "nige"

        # 3連単配当解析
        tri_m = re.search(r"3連単\s*[1-6]-[1-6]-[1-6]\s*¥?([\d,]+)", res_text)
        if tri_m:
            bundle["payout"] = int(tri_m.group(1).replace(",", ""))

        wind_m = re.search(r"風速\s*(\d+)\s*m", res_text)
        wave_m = re.search(r"波高\s*(\d+)\s*cm", res_text)
        if wind_m:
            bundle["windSpeed"] = int(wind_m.group(1))
        if wave_m:
            bundle["wave"] = int(wave_m.group(1))

        return bundle
    except Exception as e:
        return {"status": "error", "message": f"結果データ取得エラー: {e}"}


EMBEDDED_REVIEWER_HTML = r"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>🎓 ぼーとだいがくせい｜レース結果×予想 振り返りアナライザー (POST-RACE REVIEW LAB)</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
      body { background: #090d16; color: #f8fafc; font-family: sans-serif; margin: 0; }
      .boat-1 { background: #ffffff; color: #0f172a; border: 1px solid #cbd5e1; }
      .boat-2 { background: #1e293b; color: #ffffff; border: 1px solid #64748b; }
      .boat-3 { background: #ef4444; color: #ffffff; }
      .boat-4 { background: #3b82f6; color: #ffffff; }
      .boat-5 { background: #eab308; color: #0f172a; }
      .boat-6 { background: #22c55e; color: #ffffff; }
      input[type="number"], select, input[type="date"], input[type="text"], textarea {
        background: #131c2e; border: 1px solid #2dd4bf40; color: #f8fafc;
        border-radius: 0.375rem; padding: 0.25rem 0.45rem; font-size: 0.78rem;
      }
      .slit-lane {
        position: relative; height: 42px; border-bottom: 1px dashed #1e293b;
        display: flex; align-items: center;
      }
      .kado-line { border-top: 2px dashed #f43f5e !important; }
    </style>
  </head>
  <body class="pb-14">
    <!-- Header -->
    <header class="sticky top-0 z-30 bg-slate-950/95 border-b border-teal-500/30 px-3 py-2.5 shadow-lg backdrop-blur">
      <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-2">
        <div class="flex items-center gap-2">
          <span class="bg-teal-400 text-slate-950 font-black px-2 py-0.5 rounded text-xs">POST-RACE REVIEW LAB</span>
          <h1 class="text-sm md:text-base font-bold text-white">
            🎓 ぼーとだいがくせい｜レース結果×予想 答え合わせ＆敗因解剖アナライザー
          </h1>
          <span id="headerStatusBadge" class="text-[11px] font-bold text-teal-300 ml-1"></span>
        </div>

        <div class="flex flex-wrap items-center gap-1.5 text-xs">
          <button onclick="document.getElementById('pasteResultModal').classList.toggle('hidden')" class="bg-teal-600 hover:bg-teal-500 text-slate-950 font-black px-2.5 py-1 rounded shadow">
            📥 公式「結果ページ」コピペ取込
          </button>
          <button onclick="loadSampleCase('makuri_hit')" class="bg-slate-800 hover:bg-slate-700 text-amber-300 border border-amber-500/40 px-2 py-1 rounded">
            例①: 3カドまくり的中
          </button>
          <button onclick="loadSampleCase('sashi_miss')" class="bg-slate-800 hover:bg-slate-700 text-rose-300 border border-rose-500/40 px-2 py-1 rounded">
            例②: イン買い→2差・展開待ち抜け
          </button>
          <button onclick="loadSampleCase('in_hit')" class="bg-slate-800 hover:bg-slate-700 text-sky-300 border border-sky-500/40 px-2 py-1 rounded">
            例③: イン逃げ本線的中
          </button>
          <a href="https://x.com/Boatrace__daisu" target="_blank" rel="noopener" class="bg-slate-900 hover:bg-slate-800 text-white border border-slate-600 px-2 py-1 rounded font-bold">
            𝕏 @Boatrace__daisu
          </a>
          <a href="https://note.com/boatrace__daisu" target="_blank" rel="noopener" class="bg-emerald-950 hover:bg-emerald-900 text-emerald-300 border border-emerald-600/50 px-2 py-1 rounded font-bold">
            📓 note
          </a>
        </div>
      </div>
    </header>

    <main class="max-w-7xl mx-auto px-3 pt-3 space-y-3">
      <!-- 公式結果テキストコピペ取込ボックス -->
      <section id="pasteResultModal" class="hidden bg-slate-900 border-2 border-teal-500/50 rounded-xl p-3 space-y-2">
        <div class="flex items-center justify-between border-b border-slate-800 pb-1">
          <h2 class="text-xs font-bold text-teal-300">📥 BOAT RACE公式「レース結果」ページの全文コピペ一括取込</h2>
          <button onclick="document.getElementById('pasteResultModal').classList.add('hidden')" class="text-xs text-slate-400 hover:text-white">✕ 閉じる</button>
        </div>
        <textarea id="rawResultPasteInput" rows="4" placeholder="BOAT RACE公式の「結果（raceresult）」ページを全選択コピー（Ctrl+A → Ctrl+C）してここに貼り付けると、1〜6着順・選手名・本番進入・本番ST・決まり手・3連単配当・風速を自動で読み取ります。" class="w-full bg-slate-950 border border-slate-700 rounded p-2 text-xs font-mono text-slate-200"></textarea>
        <div class="flex justify-end gap-2">
          <button onclick="parsePastedOfficialResult()" class="bg-teal-400 hover:bg-teal-300 text-slate-950 font-black text-xs px-4 py-1.5 rounded shadow">⚡ 結果テキストを解析して反映する</button>
        </div>
      </section>

      <div class="grid grid-cols-1 lg:grid-cols-12 gap-4">
        <!-- 左カラム (6 cols): ①実際のレース結果入力 ＋ ②あなたの事前予想入力 ＋ ③展示ST vs 本番ST比較 -->
        <section class="lg:col-span-6 space-y-3">
          <!-- ① 確定したレース結果データ -->
          <div class="bg-slate-900 border border-teal-500/30 rounded-xl p-3 space-y-2.5">
            <div class="flex flex-wrap items-center justify-between gap-1 border-b border-slate-800 pb-1.5">
              <h2 class="text-xs font-bold text-teal-300">🏁 ① 確定したレース結果（着順・決まり手・配当・気象）</h2>
              <span class="text-[10px] text-slate-400">数値を変えるとリアルタイムで敗因・勝因を再解剖します</span>
            </div>

            <div class="grid grid-cols-2 sm:grid-cols-6 gap-2 text-xs">
              <div>
                <label class="block text-slate-400 text-[10px]">レース場</label>
                <select id="revVenue" onchange="runReviewAnalysis()" class="w-full font-bold">
                  <option value="桐生">01 桐生</option><option value="戸田">02 戸田</option><option value="江戸川">03 江戸川</option>
                  <option value="平和島" selected>04 平和島</option><option value="多摩川">05 多摩川</option><option value="浜名湖">06 浜名湖</option>
                  <option value="蒲郡">07 蒲郡</option><option value="常滑">08 常滑</option><option value="津">09 津</option>
                  <option value="三国">10 三国</option><option value="びわこ">11 びわこ</option><option value="住之江">12 住之江</option>
                  <option value="尼崎">13 尼崎</option><option value="鳴門">14 鳴門</option><option value="丸亀">15 丸亀</option>
                  <option value="児島">16 児島</option><option value="宮島">17 宮島</option><option value="徳山">18 徳山</option>
                  <option value="下関">19 下関</option><option value="若松">20 若松</option><option value="芦屋">21 芦屋</option>
                  <option value="福岡">22 福岡</option><option value="唐津">23 唐津</option><option value="大村">24 大村</option>
                </select>
              </div>
              <div>
                <label class="block text-slate-400 text-[10px]">R / グレード</label>
                <div class="flex gap-1">
                  <select id="revRaceNo" onchange="runReviewAnalysis()" class="w-1/2 font-bold text-amber-300">
                    <option value="1">1R</option><option value="2">2R</option><option value="3">3R</option><option value="4">4R</option>
                    <option value="5">5R</option><option value="6">6R</option><option value="7">7R</option><option value="8">8R</option>
                    <option value="9">9R</option><option value="10">10R</option><option value="11">11R</option><option value="12" selected>12R</option>
                  </select>
                  <select id="revGrade" onchange="runReviewAnalysis()" class="w-1/2 font-bold text-amber-200">
                    <option value="一般">一般</option><option value="G3">G3</option><option value="G2">G2</option>
                    <option value="G1" selected>G1</option><option value="PG1">PG1</option><option value="SG">SG</option>
                  </select>
                </div>
              </div>
              <div>
                <label class="block text-teal-300 font-bold text-[10px]">確定 1着-2着-3着</label>
                <div class="flex gap-1">
                  <select id="fin1" onchange="runReviewAnalysis()" class="w-1/3 font-black text-amber-300"><option value="1">1</option><option value="2">2</option><option value="3" selected>3</option><option value="4">4</option><option value="5">5</option><option value="6">6</option></select>
                  <select id="fin2" onchange="runReviewAnalysis()" class="w-1/3 font-black text-slate-200"><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4" selected>4</option><option value="5">5</option><option value="6">6</option></select>
                  <select id="fin3" onchange="runReviewAnalysis()" class="w-1/3 font-black text-amber-600"><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option><option value="5" selected>5</option><option value="6">6</option></select>
                </div>
              </div>
              <div>
                <label class="block text-teal-300 font-bold text-[10px]">実際の決まり手</label>
                <select id="actualKimarite" onchange="runReviewAnalysis()" class="w-full font-bold text-rose-300">
                  <option value="nige">🛡️ 逃げ</option>
                  <option value="sashi">📐 差し</option>
                  <option value="makuri" selected>🔥 まくり</option>
                  <option value="makurisashi">⚡ まくり差し</option>
                  <option value="nuki">🌀 抜き(道中逆転)</option>
                  <option value="megumare">⚠️ 恵まれ(F/事故)</option>
                </select>
              </div>
              <div>
                <label class="block text-slate-400 text-[10px]">3連単払戻(円)</label>
                <input type="number" id="payoutYen" value="4820" step="10" min="100" onchange="runReviewAnalysis()" class="w-full font-mono font-bold text-amber-300" />
              </div>
              <div>
                <label class="block text-slate-400 text-[10px]">風向/風速(m)/波(cm)</label>
                <div class="flex gap-1">
                  <select id="actualWindDir" onchange="runReviewAnalysis()" class="w-1/2">
                    <option value="向かい風" selected>向風</option><option value="追い風">追風</option><option value="横風">横風</option><option value="無風">無風</option>
                  </select>
                  <input type="number" id="actualWindSpeed" value="4" min="0" max="15" onchange="runReviewAnalysis()" class="w-1/4" title="風速(m)" />
                  <input type="number" id="actualWave" value="3" min="0" max="30" onchange="runReviewAnalysis()" class="w-1/4" title="波高(cm)" />
                </div>
              </div>
            </div>

            <!-- 6艇の展示ST vs 本番ST ＆ 1M実際の動きテーブル -->
            <div class="pt-2 border-t border-slate-800">
              <div class="flex items-center justify-between mb-1">
                <span class="text-[11px] font-bold text-slate-300">⏱️ コース別【事前想定(展示)ST vs 本番実ST】＆ 1マーク実際の動き</span>
                <span class="text-[10px] text-slate-400">カド位置: <select id="actualKado" onchange="runReviewAnalysis()" class="text-[10px] py-0 px-1"><option value="3" selected>3カド</option><option value="4">4カド</option><option value="5">5カド</option></select></span>
              </div>
              <div class="overflow-x-auto">
                <table class="w-full text-xs text-left">
                  <thead class="text-[10px] text-slate-400 border-b border-slate-800">
                    <tr>
                      <th class="py-1">進入</th>
                      <th class="py-1">艇・選手名</th>
                      <th class="py-1 text-center">展示時計</th>
                      <th class="py-1 text-center">事前/展示ST</th>
                      <th class="py-1 text-center text-teal-300">本番実ST</th>
                      <th class="py-1 text-center">ST変化</th>
                      <th class="py-1 text-center">確定着順</th>
                    </tr>
                  </thead>
                  <tbody id="boatStInputTable" class="divide-y divide-slate-800/60"></tbody>
                </table>
              </div>
            </div>
          </div>

          <!-- ② あなたの事前予想（買い目・想定展開・投資金額） -->
          <div class="bg-slate-900 border border-pink-500/40 rounded-xl p-3 space-y-2.5">
            <div class="flex flex-wrap items-center justify-between gap-1 border-b border-slate-800 pb-1.5">
              <h2 class="text-xs font-bold text-pink-300">🎯 ② あなたが事前に予想していた内容（買い目・想定展開・投資金額）</h2>
              <span class="text-[10px] text-slate-400">単発 `1-2-3` やフォーメーション `1-23-2345` に対応</span>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
              <div>
                <label class="block text-slate-400 text-[10px]">事前の本命シナリオ</label>
                <select id="preExpectedScenario" onchange="runReviewAnalysis()" class="w-full font-bold text-pink-200">
                  <option value="nige">🛡️ 1コースイン逃げ本線</option>
                  <option value="sashi">📐 2・3コース差し逆転</option>
                  <option value="makuri" selected>🔥 3・4コースまくり一撃</option>
                  <option value="makurisashi">⚡ センターまくり差し</option>
                  <option value="tenkaimachi">⏳ 展開待ち高配当狙い</option>
                  <option value="two_pattern">🔄 イン逃げ＋非インの2パターン</option>
                </select>
              </div>
              <div>
                <label class="block text-slate-400 text-[10px]">1点あたり or 総投資額(円)</label>
                <input type="number" id="totalInvestYen" value="4000" step="100" min="100" onchange="runReviewAnalysis()" class="w-full font-mono font-bold text-amber-300" />
              </div>
              <div>
                <label class="block text-slate-400 text-[10px]">的中時の購入金額(円/1点)</label>
                <input type="number" id="hitTicketYen" value="500" step="100" min="100" onchange="runReviewAnalysis()" class="w-full font-mono font-bold text-emerald-300" />
              </div>
            </div>

            <div>
              <label class="block text-slate-400 text-[10px] mb-1">事前購入・予想していた3連単買い目（カンマ・スペース・フォーメーション可）</label>
              <textarea id="preBetsInput" rows="2" oninput="runReviewAnalysis()" class="w-full bg-slate-950 border border-pink-500/40 rounded p-2 text-xs font-mono text-white">1-2-4, 1-4-2, 3-4-5, 3-4-1, 3-5-4, 4-5-1</textarea>
            </div>
          </div>

          <!-- ③ 事前想定スリット vs 本番実スリット 比較ビジュアルマップ -->
          <div class="bg-slate-900 border border-slate-800 rounded-xl p-3 space-y-2">
            <div class="flex items-center justify-between">
              <h2 class="text-xs font-bold text-teal-400">📊 ③ 事前想定スリット vs 本番実スリット 比較マップ</h2>
              <span class="text-[10px] text-slate-400">半透明＝展示/事前ST ／ 実線バッジ＝本番実ST</span>
            </div>
            <div class="bg-slate-950 border border-slate-800 rounded-lg p-2 relative overflow-hidden">
              <div class="absolute right-10 top-0 bottom-0 w-0.5 bg-teal-400 shadow-[0_0_8px_#2dd4bf] z-10"></div>
              <div class="absolute right-11 top-1 text-[9px] text-teal-300 font-bold">START</div>
              <div id="slitComparisonLanes"></div>
            </div>
          </div>
        </section>

        <!-- 右カラム (6 cols): ④結果×予想 答え合わせ総合判定 ＋ ⑤シミュレーター設定フィードバック処方箋 ＋ ⑥X/note振り返り投稿生成 ＋ ⑦収支・研究履歴ログ -->
        <section class="lg:col-span-6 space-y-3">
          <!-- ④ 答え合わせ総合ジャッジ＆5段階敗因/勝因解剖 -->
          <div class="bg-slate-900 border-2 border-teal-500/40 rounded-xl p-3 space-y-2.5">
            <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-2">
              <div class="flex items-center gap-2">
                <span id="hitOrMissBadge" class="px-3 py-1 rounded font-black text-sm">解析中</span>
                <div>
                  <div id="resultSummaryTitle" class="text-xs font-bold text-white"></div>
                  <div id="roiSummaryText" class="text-[11px] font-mono text-amber-300"></div>
                </div>
              </div>
              <button onclick="saveCurrentReviewToLog()" class="bg-teal-500 hover:bg-teal-400 text-slate-950 font-black text-xs px-3 py-1.5 rounded shadow">
                💾 このレースを研究履歴に保存
              </button>
            </div>

            <!-- 5段階解剖レポート -->
            <div id="retrospectiveDetailBox" class="text-xs leading-relaxed text-slate-200 bg-slate-950/90 border border-slate-800 rounded-lg p-3 space-y-2.5"></div>
          </div>

          <!-- ⑤ 予想シミュレーター（PHASE 2 PRO）への改善フィードバック処方箋 -->
          <div class="bg-slate-900 border border-amber-500/40 rounded-xl p-3 space-y-2">
            <div class="flex items-center justify-between">
              <h2 class="text-xs font-bold text-amber-300">🛠️ ⑤ 次レースに向けた「予想シミュレーター」設定調整処方箋</h2>
              <span class="text-[10px] bg-amber-950 text-amber-300 border border-amber-700/50 px-2 py-0.5 rounded">重み付け＆戦法フィードバック</span>
            </div>
            <div id="simulatorPrescriptionBox" class="text-xs leading-relaxed text-slate-200 bg-slate-950/80 border border-slate-800 rounded-lg p-2.5 space-y-1.5"></div>
          </div>

          <!-- ⑥ X (@Boatrace__daisu) & note 振り返り・的中報告／検証レポート出力 -->
          <div class="bg-slate-900 border-2 border-sky-500/40 rounded-xl p-3 space-y-2">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div>
                <h2 class="text-xs font-bold text-sky-300">📝 ⑥ X (旧Twitter) ＆ note用「レース後振り返り・的中/検証レポート」自動生成</h2>
                <span class="text-[10px] text-slate-400">的中時は「展開読みの的中報告」、不的中時はフォロワーの信頼を高める「1M原因検証ログ」を出力</span>
              </div>
              <div class="flex items-center gap-1.5 text-xs">
                <select id="postReportMode" onchange="runReviewAnalysis()" class="font-bold text-sky-200">
                  <option value="auto" selected>🤖 的中/不的中に応じて自動切替</option>
                  <option value="x_hit">🎉 X用：的中＆展開完全一致報告</option>
                  <option value="x_verify">🔬 X用：1Mスリット＆展開検証ログ</option>
                  <option value="note_retro">📓 note追記・振り返り記事用(長文)</option>
                </select>
                <button onclick="copyRetroReport()" class="bg-sky-500 hover:bg-sky-400 text-slate-950 font-black px-2.5 py-1 rounded text-[11px] shadow">
                  レポートをコピー
                </button>
              </div>
            </div>
            <div id="copyRetroToast" class="hidden text-[11px] text-emerald-300 bg-emerald-950/70 border border-emerald-700/50 rounded px-2 py-1">
              振り返りレポートをクリップボードにコピーしました！
            </div>
            <textarea id="retroReportTextarea" rows="13" readonly class="w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-[11px] font-mono text-slate-200 leading-relaxed focus:outline-none"></textarea>
          </div>

          <!-- ⑦ 本日の研究・収支履歴ログ（累計的中率・回収率・傾向分析） -->
          <div class="bg-slate-900 border border-slate-800 rounded-xl p-3 space-y-2">
            <div class="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800 pb-1.5">
              <div>
                <h2 class="text-xs font-bold text-emerald-400">📈 ⑦ 累計レース振り返り履歴 ＆ 収支・弱点傾向サマリー</h2>
                <span id="logStatsSummary" class="text-[11px] font-mono text-slate-300">保存履歴: 0件</span>
              </div>
              <button onclick="clearReviewLogs()" class="text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-400 px-2 py-0.5 rounded">履歴クリア</button>
            </div>
            <div id="reviewLogsContainer" class="space-y-1.5 max-h-[220px] overflow-y-auto text-xs"></div>
          </div>
        </section>
      </div>
    </main>

    <script>
      let reviewBoats = {};
      let reviewLogs = [];

      const KIMARITE_LABELS = {
        nige: "逃げ",
        sashi: "差し",
        makuri: "まくり",
        makurisashi: "まくり差し",
        nuki: "抜き",
        megumare: "恵まれ"
      };

      function loadSampleCase(mode) {
        if (mode === "makuri_hit") {
          document.getElementById("revVenue").value = "平和島";
          document.getElementById("revRaceNo").value = "12";
          document.getElementById("revGrade").value = "G1";
          document.getElementById("fin1").value = "3";
          document.getElementById("fin2").value = "4";
          document.getElementById("fin3").value = "5";
          document.getElementById("actualKimarite").value = "makuri";
          document.getElementById("payoutYen").value = "4820";
          document.getElementById("actualWindDir").value = "向かい風";
          document.getElementById("actualWindSpeed").value = "4";
          document.getElementById("actualWave").value = "3";
          document.getElementById("actualKado").value = "3";
          document.getElementById("preExpectedScenario").value = "two_pattern";
          document.getElementById("totalInvestYen").value = "4000";
          document.getElementById("hitTicketYen").value = "500";
          document.getElementById("preBetsInput").value = "1-2-4, 1-4-2, 3-4-5, 3-4-1, 3-5-4, 4-5-1";

          reviewBoats = {
            1: { id: 1, course: 1, name: "白井 英治", exTime: 6.75, preSt: 0.11, actualSt: 0.14, rank: 4 },
            2: { id: 2, course: 2, name: "瓜生 正義", exTime: 6.79, preSt: 0.14, actualSt: 0.19, rank: 5 },
            3: { id: 3, course: 3, name: "澤田 尚也", exTime: 6.71, preSt: 0.13, actualSt: 0.09, rank: 1 },
            4: { id: 4, course: 4, name: "大峯 豊", exTime: 6.75, preSt: 0.13, actualSt: 0.12, rank: 2 },
            5: { id: 5, course: 5, name: "篠崎 仁志", exTime: 6.80, preSt: 0.15, actualSt: 0.13, rank: 3 },
            6: { id: 6, course: 6, name: "吉田 裕平", exTime: 6.82, preSt: 0.14, actualSt: 0.16, rank: 6 }
          };
        } else if (mode === "sashi_miss") {
          document.getElementById("revVenue").value = "福岡";
          document.getElementById("revRaceNo").value = "11";
          document.getElementById("revGrade").value = "G1";
          document.getElementById("fin1").value = "2";
          document.getElementById("fin2").value = "1";
          document.getElementById("fin3").value = "5";
          document.getElementById("actualKimarite").value = "sashi";
          document.getElementById("payoutYen").value = "3640";
          document.getElementById("actualWindDir").value = "追い風";
          document.getElementById("actualWindSpeed").value = "5";
          document.getElementById("actualWave").value = "4";
          document.getElementById("actualKado").value = "4";
          document.getElementById("preExpectedScenario").value = "nige";
          document.getElementById("totalInvestYen").value = "3600";
          document.getElementById("hitTicketYen").value = "400";
          document.getElementById("preBetsInput").value = "1-2-3, 1-2-4, 1-3-2, 1-3-4, 1-4-2, 1-4-3";

          reviewBoats = {
            1: { id: 1, course: 1, name: "峰 竜太", exTime: 6.78, preSt: 0.12, actualSt: 0.13, rank: 2 },
            2: { id: 2, course: 2, name: "毒島 誠", exTime: 6.74, preSt: 0.13, actualSt: 0.11, rank: 1 },
            3: { id: 3, course: 3, name: "馬場 貴也", exTime: 6.76, preSt: 0.14, actualSt: 0.14, rank: 4 },
            4: { id: 4, course: 4, name: "桐生 順平", exTime: 6.79, preSt: 0.15, actualSt: 0.16, rank: 5 },
            5: { id: 5, course: 5, name: "茅原 悠紀", exTime: 6.75, preSt: 0.14, actualSt: 0.13, rank: 3 },
            6: { id: 6, course: 6, name: "池田 浩二", exTime: 6.81, preSt: 0.16, actualSt: 0.17, rank: 6 }
          };
        } else {
          document.getElementById("revVenue").value = "大村";
          document.getElementById("revRaceNo").value = "12";
          document.getElementById("revGrade").value = "SG";
          document.getElementById("fin1").value = "1";
          document.getElementById("fin2").value = "2";
          document.getElementById("fin3").value = "4";
          document.getElementById("actualKimarite").value = "nige";
          document.getElementById("payoutYen").value = "980";
          document.getElementById("actualWindDir").value = "無風";
          document.getElementById("actualWindSpeed").value = "1";
          document.getElementById("actualWave").value = "1";
          document.getElementById("actualKado").value = "4";
          document.getElementById("preExpectedScenario").value = "nige";
          document.getElementById("totalInvestYen").value = "3000";
          document.getElementById("hitTicketYen").value = "1000";
          document.getElementById("preBetsInput").value = "1-2-4, 1-4-2, 1-2-3, 1-3-2";

          reviewBoats = {
            1: { id: 1, course: 1, name: "白井 英治", exTime: 6.72, preSt: 0.11, actualSt: 0.09, rank: 1 },
            2: { id: 2, course: 2, name: "瓜生 正義", exTime: 6.76, preSt: 0.13, actualSt: 0.12, rank: 2 },
            3: { id: 3, course: 3, name: "澤田 尚也", exTime: 6.79, preSt: 0.14, actualSt: 0.15, rank: 4 },
            4: { id: 4, course: 4, name: "大峯 豊", exTime: 6.74, preSt: 0.13, actualSt: 0.12, rank: 3 },
            5: { id: 5, course: 5, name: "篠崎 仁志", exTime: 6.80, preSt: 0.15, actualSt: 0.15, rank: 5 },
            6: { id: 6, course: 6, name: "吉田 裕平", exTime: 6.82, preSt: 0.16, actualSt: 0.17, rank: 6 }
          };
        }

        renderBoatStTable();
        runReviewAnalysis();
      }

      function renderBoatStTable() {
        const tbody = document.getElementById("boatStInputTable");
        tbody.innerHTML = "";
        for (let b = 1; b <= 6; b++) {
          const d = reviewBoats[b];
          const diff = d.actualSt - d.preSt;
          const diffStr = (diff >= 0 ? "+" : "") + diff.toFixed(2);
          const diffCls = diff <= -0.02 ? "text-amber-300 font-bold" : diff >= 0.03 ? "text-rose-400 font-bold" : "text-slate-400";
          const diffLabel = diff <= -0.02 ? "🚀踏み込み" : diff >= 0.03 ? "⚠️ドカ遅れ" : "通り";

          tbody.innerHTML += `
          <tr>
            <td class="py-1 font-bold text-slate-300">${d.course}C</td>
            <td class="py-1 flex items-center gap-1.5">
              <span class="boat-${b} w-5 h-5 rounded text-[11px] font-black flex items-center justify-center">${b}</span>
              <input type="text" value="${d.name}" onchange="updateRevBoat(${b},'name',this.value)" class="w-24 bg-slate-950 px-1 py-0.5 text-xs font-bold" />
            </td>
            <td class="py-1 text-center"><input type="number" step="0.01" value="${d.exTime.toFixed(2)}" onchange="updateRevBoat(${b},'exTime',parseFloat(this.value))" class="w-14 text-center font-mono" /></td>
            <td class="py-1 text-center"><input type="number" step="0.01" value="${d.preSt.toFixed(2)}" onchange="updateRevBoat(${b},'preSt',parseFloat(this.value))" class="w-14 text-center font-mono text-slate-300" /></td>
            <td class="py-1 text-center"><input type="number" step="0.01" value="${d.actualSt.toFixed(2)}" onchange="updateRevBoat(${b},'actualSt',parseFloat(this.value))" class="w-14 text-center font-mono text-teal-300 font-bold" /></td>
            <td class="py-1 text-center font-mono text-[10px] ${diffCls}">${diffStr} (${diffLabel})</td>
            <td class="py-1 text-center"><input type="number" min="1" max="6" value="${d.rank}" onchange="updateRevBoat(${b},'rank',parseInt(this.value,10))" class="w-11 text-center font-bold" /></td>
          </tr>`;
        }
      }

      function updateRevBoat(b, key, val) {
        reviewBoats[b][key] = val;
        renderBoatStTable();
        runReviewAnalysis();
      }

      function parseUserBets(rawStr) {
        if (!rawStr) return [];
        const tokens = rawStr.replace(/、|，|\n|\r|\t/g, ",").split(/[,\s]+/).map(s => s.trim()).filter(Boolean);
        const comboSet = new Set();
        const expandDigits = (part) => {
          if (part === "全" || part === "9" || part.toUpperCase() === "ALL") return [1, 2, 3, 4, 5, 6];
          return [...part.matchAll(/[1-6]/g)].map(m => Number(m[0]));
        };
        tokens.forEach(tok => {
          const parts = tok.split(/[-=→>]/);
          if (parts.length === 3) {
            const p1 = expandDigits(parts[0]), p2 = expandDigits(parts[1]), p3 = expandDigits(parts[2]);
            p1.forEach(a => p2.forEach(b => p3.forEach(c => {
              if (a !== b && b !== c && a !== c) comboSet.add(`${a}-${b}-${c}`);
            })));
          } else if (/^[1-6]{3}$/.test(tok)) {
            const a = Number(tok[0]), b = Number(tok[1]), c = Number(tok[2]);
            if (a !== b && b !== c && a !== c) comboSet.add(`${a}-${b}-${c}`);
          }
        });
        return Array.from(comboSet);
      }

      function renderSlitComparison() {
        const container = document.getElementById("slitComparisonLanes");
        const kado = Number(document.getElementById("actualKado").value);
        container.innerHTML = "";
        for (let b = 1; b <= 6; b++) {
          const d = reviewBoats[b];
          const preLeft = Math.max(12, Math.min(72, 42 + (0.16 - d.preSt) * 280));
          const actLeft = Math.max(12, Math.min(75, 42 + (0.16 - d.actualSt) * 280));
          const diff = d.actualSt - d.preSt;
          const badge = diff <= -0.02 ? "🚀本番踏み込み" : diff >= 0.03 ? "⚠️本番凹み" : "";
          container.innerHTML += `
          <div class="slit-lane ${d.course === kado ? "kado-line" : ""}">
            <span class="text-[10px] text-slate-400 w-12 pl-1 font-mono">${d.course}C</span>
            <!-- 事前想定ST (半透明ゴースト) -->
            <div style="left:${preLeft}%;" class="absolute flex items-center opacity-35 pointer-events-none">
              <span class="boat-${b} px-1.5 py-0.5 rounded text-[10px] font-bold">${b}</span>
              <span class="text-[9px] text-slate-300 ml-1">展.${Math.round(d.preSt * 100).toString().padStart(2, "0")}</span>
            </div>
            <!-- 本番実ST -->
            <div style="left:${actLeft}%;" class="absolute flex items-center gap-1.5 z-10">
              <span class="boat-${b} px-2 py-0.5 rounded text-xs font-black shadow">${b}</span>
              <span class="text-[11px] font-bold text-white whitespace-nowrap">${d.name.replace(/\s+/g, "")} <span class="font-mono text-teal-300">(実.${Math.round(d.actualSt * 100).toString().padStart(2, "0")})</span> <span class="text-[10px] text-amber-300">${badge}</span></span>
            </div>
          </div>`;
        }
      }

      function runReviewAnalysis() {
        renderSlitComparison();

        const venue = document.getElementById("revVenue").value;
        const raceNo = document.getElementById("revRaceNo").value;
        const grade = document.getElementById("revGrade").value;
        const f1 = Number(document.getElementById("fin1").value);
        const f2 = Number(document.getElementById("fin2").value);
        const f3 = Number(document.getElementById("fin3").value);
        const actualCombo = `${f1}-${f2}-${f3}`;
        const kimarite = document.getElementById("actualKimarite").value;
        const kimariteName = KIMARITE_LABELS[kimarite] || "逃げ";
        const payout = Number(document.getElementById("payoutYen").value || 0);
        const windDir = document.getElementById("actualWindDir").value;
        const windSpeed = Number(document.getElementById("actualWindSpeed").value || 0);
        const wave = Number(document.getElementById("actualWave").value || 0);
        const kado = Number(document.getElementById("actualKado").value || 3);

        const preScenario = document.getElementById("preExpectedScenario").value;
        const invest = Number(document.getElementById("totalInvestYen").value || 3000);
        const hitUnitYen = Number(document.getElementById("hitTicketYen").value || 500);
        const userBets = parseUserBets(document.getElementById("preBetsInput").value);

        const isHit = userBets.includes(actualCombo);
        const returnYen = isHit ? Math.round((payout / 100) * hitUnitYen) : 0;
        const profitYen = returnYen - invest;
        const roiPct = invest > 0 ? Math.round((returnYen / invest) * 100) : 0;

        // ニアミス判定
        const has1stHit = userBets.some(c => Number(c.split("-")[0]) === f1);
        const has1st2ndHit = userBets.some(c => {
          const [a, b] = c.split("-").map(Number);
          return a === f1 && b === f2;
        });
        const hasUra = userBets.includes(`${f2}-${f1}-${f3}`) || userBets.includes(`${f1}-${f3}-${f2}`);

        const hitBadge = document.getElementById("hitOrMissBadge");
        if (isHit) {
          hitBadge.className = "bg-amber-400 text-slate-950 px-3 py-1 rounded font-black text-sm shadow";
          hitBadge.textContent = "🎯 的中！ (展開一致)";
        } else if (has1st2ndHit) {
          hitBadge.className = "bg-purple-500 text-white px-3 py-1 rounded font-black text-sm shadow";
          hitBadge.textContent = "惜敗：1・2着的中 (3着抜け)";
        } else if (hasUra) {
          hitBadge.className = "bg-rose-500 text-white px-3 py-1 rounded font-black text-sm shadow";
          hitBadge.textContent = "惜敗：裏目決着 (スジ合致)";
        } else if (has1stHit) {
          hitBadge.className = "bg-sky-600 text-white px-3 py-1 rounded font-black text-sm shadow";
          hitBadge.textContent = "惜敗：1着的中 (2着スジ抜け)";
        } else {
          hitBadge.className = "bg-slate-800 text-rose-300 border border-rose-500/40 px-3 py-1 rounded font-black text-sm";
          hitBadge.textContent = "不的中 (1M展開逆行)";
        }

        const b1 = reviewBoats[f1] || { name: `${f1}号艇`, actualSt: 0.13, preSt: 0.13, exTime: 6.75 };
        const b2 = reviewBoats[f2] || { name: `${f2}号艇`, actualSt: 0.14, preSt: 0.14, exTime: 6.77 };
        const b3 = reviewBoats[f3] || { name: `${f3}号艇`, actualSt: 0.15, preSt: 0.15, exTime: 6.79 };

        document.getElementById("resultSummaryTitle").textContent =
          `${venue} ${raceNo}R (${grade}) 確定結果：${actualCombo} （${b1.name} → ${b2.name} → ${b3.name} ／ 決まり手：${kimariteName}）`;
        document.getElementById("roiSummaryText").textContent =
          `3連単配当: ${payout.toLocaleString()}円 ｜ 投資: ${invest.toLocaleString()}円 → 回収: ${returnYen.toLocaleString()}円 (収支 ${profitYen >= 0 ? "+" : ""}${profitYen.toLocaleString()}円 / 回収率 ${roiPct}%)`;

        // スリット凹み艇・踏み込み艇の特定
        const boatsArr = Object.values(reviewBoats);
        const dokaBoats = boatsArr.filter(x => x.actualSt - x.preSt >= 0.03 || x.actualSt >= 0.18);
        const topStBoat = [...boatsArr].sort((a, b) => a.actualSt - b.actualSt)[0];

        const dokaText = dokaBoats.length > 0
          ? dokaBoats.map(x => `${x.course}コース${x.id}号艇(${x.name})が展示.${Math.round(x.preSt*100).toString().padStart(2,"0")}→本番.${Math.round(x.actualSt*100).toString().padStart(2,"0")}と遅れ`).join("、")
          : "大きなスタート遅れはなく、ほぼ展示通りのスリット隊形";

        let why2nd3rdText = "";
        if (kimarite === "makuri") {
          why2nd3rdText = `${f1}号艇（${b1.name}）が本番ST .${Math.round(b1.actualSt*100).toString().padStart(2,"0")}から豪快にまくったことで内枠勢が引き波に沈み、マーク外側から連動した<strong>${f2}号艇（${b2.name}）</strong>と、1マークのもつれ・引き波を最内「展開待ち」で突いた<strong>${f3}号艇（${b3.name}）</strong>が浮上する典型的な『まくり外連動スジ』で決着しました。`;
        } else if (kimarite === "sashi" || kimarite === "makurisashi") {
          why2nd3rdText = `1マークで先マイを図ったインに対し、<strong>${f1}号艇（${b1.name}）</strong>がブイ際を鋭く${kimariteName}突破。差された${f2}号艇（${b2.name}）が2着に踏みとどまり、3着には引き波を避けて展開待ちから差した<strong>${f3}号艇（${b3.name}）</strong>が食い込みました。`;
        } else if (kimarite === "nige") {
          why2nd3rdText = `1コース<strong>${f1}号艇（${b1.name}）</strong>が本番ST .${Math.round(b1.actualSt*100).toString().padStart(2,"0")}から完璧な先マイで押し切り。2着には順当に差し・外マイ追走した<strong>${f2}号艇（${b2.name}）</strong>、3着には道中連絡みした<strong>${f3}号艇（${b3.name}）</strong>が入りました。`;
        } else {
          why2nd3rdText = `1マークの攻防からバックストレッチ・2マークでの逆転（${kimariteName}）が発生し、出足・回り足に勝る<strong>${f1}号艇→${f2}号艇→${f3}号艇</strong>の順で決着しました。`;
        }

        let reflectionAdvice = "";
        if (isHit) {
          reflectionAdvice = `✅ <strong>【勝因の解剖】</strong> 事前のスジ読み（${actualCombo}）と本番の1マーク展開（${kimariteName}）が完全に一致しています。特に2着${f2}号艇・3着${f3}号艇の連動ルートを正確に網羅できていた点が最大の勝因です。`;
        } else if (has1st2ndHit) {
          reflectionAdvice = `🔍 <strong>【3着抜けの原因解剖】</strong> 1着${f1}号艇・2着${f2}号艇の本線ラインは完璧に読めていましたが、3着に入った<strong>${f3}号艇（${b3.name}）</strong>が抜けています。1マークで${kimariteName}が起きた際、外枠や展開待ちの艇（${f3}号艇）が最内を小回りして3着に浮上するパターンを「展開待ち連対率」でケアするのが次回の改善ポイントです。`;
        } else if (has1stHit) {
          reflectionAdvice = `🔍 <strong>【2着スジ抜けの原因解剖】</strong> 1着アタマ（${f1}号艇・${kimariteName}）の狙いは的中していましたが、2着に入った<strong>${f2}号艇（${b2.name}）</strong>へのスジ連動が抜けていました。${kimarite === "makuri" ? "まくり決着時は内枠ではなく『まくった艇の1つ外（" + f2 + "号艇）』を2着筆頭に置くスジ鉄則" : "差し決着時は『1コースの2着残り』を最優先するスジ鉄則"}を徹底すると取りこぼしがなくなります。`;
        } else {
          reflectionAdvice = `🔍 <strong>【展開逆行の原因解剖】</strong> 事前は「${preScenario === "nige" ? "イン逃げ本線" : "別展開"}」を想定していましたが、本番は<strong>${dokaText}</strong>したことでスリット隊形が一変し、<strong>${f1}号艇の「${kimariteName}」</strong>が決まりました。${windDir}${windSpeed}mの水面条件と2コース壁の信頼度を再点検する必要があります。`;
        }

        document.getElementById("retrospectiveDetailBox").innerHTML = `
          <div class="space-y-1 border-b border-slate-800 pb-2">
            <div class="text-teal-300 font-bold">① スリット（展示ST vs 本番実ST）のズレ診断</div>
            <p>トップスタートは<strong>${topStBoat.course}コース${topStBoat.id}号艇（${topStBoat.name} / 実ST .${Math.round(topStBoat.actualSt*100).toString().padStart(2,"0")}）</strong>。全体としては「${dokaText}」というスリット結果でした。</p>
          </div>
          <div class="space-y-1 border-b border-slate-800 pb-2">
            <div class="text-amber-300 font-bold">② 1マーク決まり手（${kimariteName}）＆ 2・3着スジ連動の解剖</div>
            <p>${why2nd3rdText}</p>
          </div>
          <div class="space-y-1">
            <div class="text-pink-300 font-bold">③ あなたの事前予想（${userBets.length}点）に対する答え合わせ結論</div>
            <p>${reflectionAdvice}</p>
          </div>
        `;

        // ⑤ シミュレーターへの処方箋生成
        let prescriptionHtml = "";
        if (kimarite === "makuri") {
          prescriptionHtml = `
            <p>🔧 <strong>1. 重み付けスライダー調整：</strong> 本日の${venue}水面（${windDir}${windSpeed}m）ではダッシュ・スリット攻めが強く決まっています。予想シミュレーターの<strong>「④ スリット＆戦法連動ボーナス比重」を 140%〜160%</strong> に引き上げてください。</p>
            <p>🔧 <strong>2. 手動1M攻め設定：</strong> カド受け（${kado - 1}コース）のSTが不安な番組では、カド（${kado}コース）に<strong>「🔥まくり」</strong>、その外隣に<strong>「⚡まくり差し」または「⏳展開待ち」</strong>を指定した【🟥パターンB（イン逃げ以外）】の比重を高めると高配当を仕留められます。</p>
          `;
        } else if (kimarite === "sashi" || kimarite === "makurisashi") {
          prescriptionHtml = `
            <p>🔧 <strong>1. コース別攻め成功率の重視：</strong> ターンマーク際の「差し・まくり差し」が決まる水面です。予想シミュレーターの<strong>「① コース別実績・攻め成功率比重」を 130%〜150%</strong> に上げ、2コース差し率・3/4コースまくり差し率が高い選手を素直に狙ってください。</p>
            <p>🔧 <strong>2. 3着ヒモ穴対策：</strong> 差し決着の3着には<strong>「⏳展開待ち連対率」</strong>が50%を超える外枠選手を3着流しに加えると、${actualCombo}のような中穴〜万舟を取りこぼしません。</p>
          `;
        } else {
          prescriptionHtml = `
            <p>🔧 <strong>1. イン逃げ信頼度◎：</strong> 壁役の2コースがしっかり機能しインが押し切る水面です。<strong>【🟦パターンA：イン逃げ本線】</strong>を中心に、点数を6〜8点に絞って回収率（EV）を高める運用が有効です。</p>
          `;
        }
        document.getElementById("simulatorPrescriptionBox").innerHTML = prescriptionHtml;

        // ⑥ X / note 振り返りレポート生成
        let mode = document.getElementById("postReportMode").value;
        if (mode === "auto") mode = isHit ? "x_hit" : "x_verify";

        let postText = "";
        if (mode === "x_hit") {
          postText = [
            `🎯【${venue}${raceNo}R (${grade}) 展開シミュレーション完全的中！】🎯`,
            ``,
            `🏁 結果：${actualCombo} (${kimariteName} / 3連単 ${payout.toLocaleString()}円)`,
            `🥇 1着：${f1}号艇 ${b1.name} (実ST .${Math.round(b1.actualSt*100).toString().padStart(2,"0")})`,
            `🥈 2着：${f2}号艇 ${b2.name}`,
            `🥉 3着：${f3}号艇 ${b3.name}`,
            ``,
            `事前のシミュレーター解析通り、${windDir}${windSpeed}mのスリット攻防から1M「${kimariteName}」→2・3着スジ連動（${f2}号艇・${f3}号艇）がドンピシャで決まりました🚤🔥`,
            `回収率 ${roiPct}%（+${profitYen.toLocaleString()}円）達成！`,
            ``,
            `次レースの2パターン展開解析＆勝負目もnoteで公開中です👇`,
            `https://note.com/boatrace__daisu`,
            `#ぼーとだいがくせい #ボートレース #競艇予想 #${venue}競艇`
          ].join("\n");
        } else if (mode === "x_verify") {
          postText = [
            `🔬【ぼーとだいがくせいの1M展開・答え合わせ研究室】${venue}${raceNo}R (${grade})`,
            ``,
            `🏁 確定結果：${actualCombo}（決まり手：${kimariteName} / 配当 ${payout.toLocaleString()}円）`,
            `⏱️ 本番スリット変化：${dokaText}`,
            ``,
            `【1マーク解剖ログ】`,
            `${f1}号艇(${b1.name})が実ST .${Math.round(b1.actualSt*100).toString().padStart(2,"0")}から${kimariteName}。引き波と展開の隙を突いて2着に${f2}号艇(${b2.name})、3着に${f3}号艇(${b3.name})が浮上するスジ決着でした。`,
            ``,
            `本日の${venue}の水面傾向とスタート変化データをシミュレーターの重み付けに反映完了💻 次Rの予想に活かします！👇`,
            `https://note.com/boatrace__daisu`,
            `#ぼーとだいがくせい #ボートレース #競艇検証 #${venue}競艇`
          ].join("\n");
        } else {
          postText = [
            `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`,
            `🎓 ぼーとだいがくせい｜${venue}${raceNo}R (${grade}) レース結果×予想 徹底振り返りレポート`,
            `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`,
            `■ 1. 確定結果・払戻・収支判定`,
            `・確定着順: ${actualCombo} （1着:${f1}号艇 ${b1.name} → 2着:${f2}号艇 ${b2.name} → 3着:${f3}号艇 ${b3.name}）`,
            `・決まり手: ${kimariteName} ／ 3連単配当: ${payout.toLocaleString()}円`,
            `・水面気象: ${windDir}${windSpeed}m ／ 波高${wave}cm`,
            `・予想判定: ${isHit ? "🎯 的中" : "🔍 不的中（検証完了）"} （投資 ${invest.toLocaleString()}円 → 回収 ${returnYen.toLocaleString()}円 / 回収率 ${roiPct}%）`,
            ``,
            `■ 2. 展示ST vs 本番実STのズレ検証`,
            `・トップST: ${topStBoat.course}コース ${topStBoat.id}号艇 ${topStBoat.name} (実ST .${Math.round(topStBoat.actualSt*100).toString().padStart(2,"0")})`,
            `・スリット総括: ${dokaText}`,
            ``,
            `■ 3. 1マークの攻防と2・3着スジ連動の解剖`,
            why2nd3rdText.replace(/<[^>]+>/g, ""),
            ``,
            `■ 4. 次レースに向けたシミュレーター調整方針`,
            reflectionAdvice.replace(/<[^>]+>/g, ""),
            `🎓 ぼーとだいがくせい｜X: https://x.com/Boatrace__daisu ｜ note: https://note.com/boatrace__daisu`,
            `━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`
          ].join("\n");
        }
        document.getElementById("retroReportTextarea").value = postText;
      }

      function saveCurrentReviewToLog() {
        const venue = document.getElementById("revVenue").value;
        const raceNo = document.getElementById("revRaceNo").value;
        const grade = document.getElementById("revGrade").value;
        const f1 = Number(document.getElementById("fin1").value);
        const f2 = Number(document.getElementById("fin2").value);
        const f3 = Number(document.getElementById("fin3").value);
        const actualCombo = `${f1}-${f2}-${f3}`;
        const kimarite = document.getElementById("actualKimarite").value;
        const payout = Number(document.getElementById("payoutYen").value || 0);
        const invest = Number(document.getElementById("totalInvestYen").value || 3000);
        const hitUnitYen = Number(document.getElementById("hitTicketYen").value || 500);
        const userBets = parseUserBets(document.getElementById("preBetsInput").value);
        const isHit = userBets.includes(actualCombo);
        const returnYen = isHit ? Math.round((payout / 100) * hitUnitYen) : 0;

        reviewLogs.unshift({
          venue,
          raceNo,
          grade,
          actualCombo,
          kimariteName: KIMARITE_LABELS[kimarite] || "逃げ",
          payout,
          invest,
          returnYen,
          isHit
        });
        renderReviewLogs();
      }

      function clearReviewLogs() {
        reviewLogs = [];
        renderReviewLogs();
      }

      function renderReviewLogs() {
        const container = document.getElementById("reviewLogsContainer");
        const sumEl = document.getElementById("logStatsSummary");
        if (reviewLogs.length === 0) {
          sumEl.textContent = "保存履歴: 0件";
          container.innerHTML = `<div class="text-slate-500 text-[11px]">まだ保存されたレース履歴はありません。「💾 このレースを研究履歴に保存」を押すとここに蓄積されます。</div>`;
          return;
        }
        const totalRaces = reviewLogs.length;
        const hits = reviewLogs.filter(x => x.isHit).length;
        const sumInv = reviewLogs.reduce((s, x) => s + x.invest, 0);
        const sumRet = reviewLogs.reduce((s, x) => s + x.returnYen, 0);
        const roi = sumInv > 0 ? Math.round((sumRet / sumInv) * 100) : 0;
        const profit = sumRet - sumInv;

        sumEl.textContent = `全${totalRaces}R ｜ 的中 ${hits}/${totalRaces} (${Math.round((hits/totalRaces)*100)}%) ｜ 累計回収率 ${roi}% (${profit >= 0 ? "+" : ""}${profit.toLocaleString()}円)`;
        container.innerHTML = reviewLogs.map((item, idx) => `
          <div class="flex items-center justify-between bg-slate-950 border border-slate-800 px-2.5 py-1.5 rounded">
            <div class="flex items-center gap-2">
              <span class="px-1.5 py-0.5 rounded text-[10px] font-bold ${item.isHit ? "bg-amber-400 text-slate-950" : "bg-slate-800 text-slate-400"}">${item.isHit ? "🎯的中" : "不的中"}</span>
              <span class="font-bold text-white">${item.venue} ${item.raceNo}R (${item.grade})</span>
              <span class="font-mono font-bold text-teal-300">${item.actualCombo}</span>
              <span class="text-[10px] text-slate-400">[${item.kimariteName} / ${item.payout.toLocaleString()}円]</span>
            </div>
            <div class="font-mono text-[11px] ${item.returnYen - item.invest >= 0 ? "text-amber-300 font-bold" : "text-slate-400"}">
              投資${item.invest.toLocaleString()}円 → 回収${item.returnYen.toLocaleString()}円
            </div>
          </div>
        `).join("");
      }

      function copyRetroReport() {
        const txt = document.getElementById("retroReportTextarea").value;
        try {
          const ta = document.createElement("textarea");
          ta.value = txt; document.body.appendChild(ta); ta.select(); document.execCommand("copy"); document.body.removeChild(ta);
        } catch (e) {}
        const toast = document.getElementById("copyRetroToast");
        toast.classList.remove("hidden");
        setTimeout(() => toast.classList.add("hidden"), 2300);
      }

      function parsePastedOfficialResult() {
        const raw = (document.getElementById("rawResultPasteInput").value || "").trim();
        if (!raw) return;

        // 決まり手検出
        if (raw.includes("まくり差し")) document.getElementById("actualKimarite").value = "makurisashi";
        else if (raw.includes("まくり")) document.getElementById("actualKimarite").value = "makuri";
        else if (raw.includes("差し")) document.getElementById("actualKimarite").value = "sashi";
        else if (raw.includes("逃げ")) document.getElementById("actualKimarite").value = "nige";
        else if (raw.includes("抜き")) document.getElementById("actualKimarite").value = "nuki";

        // 3連単組番と配当検出
        const triMatch = raw.match(/3連単[\s\S]{1,40}?([1-6])\s*[-=]\s*([1-6])\s*[-=]\s*([1-6])[\s\S]{1,40}?¥?\s*([\d,]+)/);
        if (triMatch) {
          document.getElementById("fin1").value = triMatch[1];
          document.getElementById("fin2").value = triMatch[2];
          document.getElementById("fin3").value = triMatch[3];
          document.getElementById("payoutYen").value = parseInt(triMatch[4].replace(/,/g, ""), 10);
        }

        // 本番ST (.12 など) の抽出
        const stMatches = [...raw.matchAll(/\b0?\.(\d{2})\b/g)].map(m => parseFloat(`0.${m[1]}`));
        if (stMatches.length >= 6) {
          for (let b = 1; b <= 6; b++) {
            reviewBoats[b].actualSt = stMatches[b - 1];
          }
        }

        renderBoatStTable();
        runReviewAnalysis();
        document.getElementById("pasteResultModal").classList.add("hidden");
      }

      window.addEventListener("DOMContentLoaded", () => {
        loadSampleCase("makuri_hit");
        saveCurrentReviewToLog();
      });
    </script>
  </body>
</html>
"""

def load_html_template() -> str:
    return EMBEDDED_REVIEWER_HTML


def main():
    st.set_page_config(
        page_title="🎓 ぼーとだいがくせい｜レース結果×予想 振り返りアナライザー",
        page_icon="🔬",
        layout="wide",
    )

    st.markdown(
        """
        <style>
        .block-container { padding-top: 0.8rem !important; padding-bottom: 0.8rem !important; max-width: 1360px; }
        </style>
        """,
        unsafe_allow_html=True,
    )

    if "fetched_result_bundle" not in st.session_state:
        st.session_state["fetched_result_bundle"] = None

    c1, c2, c3, c4 = st.columns([1.1, 1.6, 0.9, 2.4])
    with c1:
        jst_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9)))
        sel_date = st.date_input("開催日", value=jst_now.date())
        hd_str = sel_date.strftime("%Y%m%d")
    with c2:
        sel_venue = st.selectbox("レース場", VENUE_LIST, index=3, format_func=lambda x: f"{x[0]} {x[1]}")
    with c3:
        sel_rno = st.selectbox("レース", list(range(1, 13)), index=11, format_func=lambda x: f"{x}R")
    with c4:
        st.write("")
        if st.button("🏁 公式レース結果＋直前展示を自動取得", type="primary", use_container_width=True):
            with st.spinner("BOAT RACE公式から確定結果と展示データを取得中..."):
                res = fetch_official_result_bundle(hd_str, sel_venue[0], sel_rno)
                if res.get("status") == "ok":
                    st.session_state["fetched_result_bundle"] = res
                    st.success(
                        f"✅ {hd_str} {sel_venue[1]} {sel_rno}R 確定結果取得：{res['fin1']}-{res['fin2']}-{res['fin3']} （配当 {res['payout']:,}円）"
                    )
                else:
                    st.error(res.get("message", "取得失敗"))

    html_str = load_html_template()
    if st.session_state["fetched_result_bundle"]:
        payload_js = json.dumps(st.session_state["fetched_result_bundle"], ensure_ascii=False)
        inject_script = f"""
        <script>
        window.addEventListener("DOMContentLoaded", () => {{
          const d = {payload_js};
          if (d && d.status === "ok") {{
            document.getElementById("revVenue").value = d.venue;
            document.getElementById("revRaceNo").value = String(d.rno);
            document.getElementById("revGrade").value = d.grade;
            document.getElementById("fin1").value = String(d.fin1);
            document.getElementById("fin2").value = String(d.fin2);
            document.getElementById("fin3").value = String(d.fin3);
            document.getElementById("actualKimarite").value = d.kimarite;
            document.getElementById("payoutYen").value = d.payout;
            document.getElementById("actualWindSpeed").value = d.windSpeed;
            document.getElementById("actualWave").value = d.wave;
            for (let b = 1; b <= 6; b++) {{
              if (d.boats[String(b)]) reviewBoats[b] = d.boats[String(b)];
            }}
            renderBoatStTable();
            runReviewAnalysis();
          }}
        }});
        </script>
        """
        html_str = html_str.replace("</body>", inject_script + "</body>")

    components.html(html_str, height=1680, scrolling=True)


if __name__ == "__main__":
    main()

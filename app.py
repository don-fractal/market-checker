import streamlit as st
import yfinance as yf
import feedparser
import requests
import io
from datetime import datetime, timedelta, timezone
import pandas as pd

# ── ページ設定 ──────────────────────────────────────────────
st.set_page_config(
    page_title="相場チェッカー",
    page_icon="📊",
    layout="centered",
    initial_sidebar_state="collapsed"
)

st.markdown("""
<style>
.block-container { padding-top: 1rem; padding-bottom: 3rem; }
.stCode pre { font-size: 12px !important; white-space: pre-wrap !important; }
.stDataFrame { font-size: 13px; }
div[data-testid="stExpander"] { margin-bottom: 6px; }
</style>
""", unsafe_allow_html=True)

# ── 取得する銘柄定義（yfinance） ─────────────────────────────
TICKERS = {
    'ドル円':         ('USDJPY=X',  '円'),
    'ユーロドル':     ('EURUSD=X',  ''),
    'DXY':            ('DX-Y.NYB',  ''),
    '日経平均':       ('^N225',     '円'),
    'S&P500':         ('^GSPC',     ''),
    'NASDAQ':         ('^IXIC',     ''),
    '上海総合':       ('000001.SS', ''),
    '原油(WTI)':     ('CL=F',      '$'),
    '金':             ('GC=F',      '$'),
    '銅':             ('HG=F',      '$'),
    '米10年債利回り': ('^TNX',      '%'),
    'BTC':            ('BTC-USD',   '$'),
    'ETH':            ('ETH-USD',   '$'),
    'VIX':            ('^VIX',      ''),
}

FRED_RATES = {
    '米2年債利回り':    ('DGS2',            '日次'),
    '米30年債利回り':   ('DGS30',           '日次'),
    '日本10年債利回り': ('IRLTLT01JPM156N', '月次'),
}

NEWS_FEEDS = [
    ('Reuters',  'https://feeds.reuters.com/reuters/businessNews'),
    ('NHK経済',  'https://www3.nhk.or.jp/rss/news/cat6.xml'),
]

CAL_COUNTRIES = {'US', 'JP', 'EU', 'GB', 'CN', 'AU', 'CA', 'DE', 'FR'}

# ── 市場反応確認用ティッカー ────────────────────────────────
REACTION_TICKERS = {
    'S&P500': '^GSPC',
    'ドル円':  'USDJPY=X',
    '米10年債': '^TNX',
}

# ── データ取得（yfinance / 5分キャッシュ） ──────────────────
@st.cache_data(ttl=300)
def fetch_market_data():
    results = {}
    for name, (ticker, unit) in TICKERS.items():
        try:
            hist = yf.Ticker(ticker).history(period='5d')
            if len(hist) >= 2:
                prev = hist['Close'].iloc[-2]
                curr = hist['Close'].iloc[-1]
                chg  = curr - prev
                pct  = chg / prev * 100
                results[name] = dict(value=curr, change=chg, pct=pct, unit=unit, ok=True)
            elif len(hist) == 1:
                results[name] = dict(value=hist['Close'].iloc[-1], change=0, pct=0, unit=unit, ok=True)
            else:
                results[name] = dict(value=None, ok=False)
        except Exception:
            results[name] = dict(value=None, ok=False)
    return results

# ── FRED 経由の金利取得（1時間キャッシュ） ──────────────────
@st.cache_data(ttl=3600)
def fetch_fred_rates():
    results = {}
    for name, (series_id, freq) in FRED_RATES.items():
        try:
            url  = f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series_id}'
            resp = requests.get(url, timeout=10)
            df   = pd.read_csv(io.StringIO(resp.text), na_values=['.'])
            df   = df.dropna()
            col  = df.columns[1]
            if len(df) >= 2:
                curr = float(df[col].iloc[-1])
                prev = float(df[col].iloc[-2])
                chg  = curr - prev
                pct  = (chg / prev * 100) if prev != 0 else 0.0
                results[name] = dict(value=curr, change=chg, pct=pct,
                                     unit='%', freq=freq, ok=True)
            elif len(df) == 1:
                results[name] = dict(value=float(df[col].iloc[-1]), change=0,
                                     pct=0, unit='%', freq=freq, ok=True)
            else:
                results[name] = dict(value=None, ok=False)
        except Exception:
            results[name] = dict(value=None, ok=False)
    return results

# ── 経済指標カレンダー（TradingView / 1時間キャッシュ） ───────
@st.cache_data(ttl=3600)
def fetch_economic_calendar():
    try:
        now     = datetime.now(timezone.utc)
        from_dt = (now - timedelta(days=7)).strftime('%Y-%m-%dT00:00:00.000Z')
        to_dt   = (now + timedelta(days=10)).strftime('%Y-%m-%dT23:59:59.000Z')
        url     = 'https://economic-calendar.tradingview.com/events'
        params  = {'from': from_dt, 'to': to_dt}
        headers = {
            'Origin':     'https://www.tradingview.com',
            'Referer':    'https://www.tradingview.com/',
            'User-Agent': 'Mozilla/5.0',
        }
        resp   = requests.get(url, params=params, headers=headers, timeout=15)
        events = resp.json().get('result', [])
        return [e for e in events
                if e.get('importance', -1) >= 1
                and e.get('country', '') in CAL_COUNTRIES]
    except Exception:
        return []

# ── 過去10日間の日次価格データ（市場反応計算用 / 1時間キャッシュ） ──
@st.cache_data(ttl=3600)
def fetch_daily_prices():
    result = {}
    for name, ticker in REACTION_TICKERS.items():
        try:
            h = yf.Ticker(ticker).history(period='15d', interval='1d')
            if not h.empty:
                result[name] = h['Close']
        except Exception:
            pass
    return result

# ── ニュース取得（10分キャッシュ） ──────────────────────────
@st.cache_data(ttl=600)
def fetch_news():
    articles = []
    for source, url in NEWS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for e in feed.entries[:5]:
                articles.append({'source': source, 'title': e.get('title', '').strip()})
        except Exception:
            pass
    return articles[:10]

# ── 表示フォーマット ────────────────────────────────────────
def fmt_val(d):
    if not d.get('ok') or d['value'] is None:
        return 'N/A'
    v, u = d['value'], d['unit']
    if u == '$':
        return f"${v:,.2f}" if v < 10000 else f"${v:,.0f}"
    elif u == '円':
        return f"{v:,.2f}円"
    elif u == '%':
        return f"{v:.3f}%"
    else:
        return f"{v:.4f}"

def fmt_chg(d):
    if not d.get('ok') or d['value'] is None:
        return 'N/A'
    p = d['pct']
    arrow = '▲' if p > 0 else '▼' if p < 0 else '－'
    return f"{arrow}{abs(p):.2f}%"

def fmt_chg_bp(d):
    if not d.get('ok') or d['value'] is None:
        return 'N/A'
    bp = round(d.get('change', 0) * 100)
    if bp > 0: return f"+{bp}bp"
    if bp < 0: return f"{bp}bp"
    return "±0bp"

def fmt_pct(pct):
    if pct is None: return '-'
    arrow = '▲' if pct > 0 else '▼' if pct < 0 else '－'
    return f"{arrow}{abs(pct):.2f}%"

def vix_status(d):
    if not d.get('ok') or d['value'] is None:
        return ''
    v = d['value']
    if v < 15:  return '😌 極平穏'
    if v < 20:  return '😊 平穏'
    if v < 25:  return '😐 要注意'
    if v < 30:  return '😟 警戒'
    return '😰 要警戒'

def fmt_event_val(val, event):
    if val is None:
        return '-'
    try:
        val = float(val)
    except (ValueError, TypeError):
        return str(val)
    scale = event.get('scale', '')
    unit  = event.get('unit', '')
    if scale == 'K':
        return f"{val:+.0f}K" if isinstance(val, (int, float)) else str(val)
    elif scale == 'M':
        return f"{val:.0f}M"
    elif scale == 'B':
        return f"{val:.1f}B"
    elif unit == '%':
        return f"{val:.1f}%"
    else:
        s = f"{val:.2f}".rstrip('0').rstrip('.')
        return f"{s}{unit}" if unit else s

WEEKDAY_JP = {'Mon': '月', 'Tue': '火', 'Wed': '水', 'Thu': '木',
              'Fri': '金', 'Sat': '土', 'Sun': '日'}

def utc_to_jst_str(date_str):
    try:
        dt  = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        jst = dt + timedelta(hours=9)
        s   = jst.strftime('%m/%d(%a) %H:%M')
        for en, jp in WEEKDAY_JP.items():
            s = s.replace(en, jp)
        return s
    except Exception:
        return date_str

def yield_curve_status(us2, us10):
    if not us2.get('ok') or not us10.get('ok'):
        return None, None
    v2, v10 = us2['value'], us10['value']
    spread  = v10 - v2
    if spread < -0.3:
        label = f"⚠️ 深刻な逆イールド ({spread:+.2f}%)"
    elif spread < 0:
        label = f"⚠️ 逆イールド ({spread:+.2f}%)"
    elif spread < 0.3:
        label = f"➡️ フラット ({spread:+.2f}%)"
    else:
        label = f"✅ 正常 ({spread:+.2f}%)"
    return spread, label

# ── 指標発表日の市場反応を計算 ──────────────────────────────
def get_event_reaction(event, daily_prices):
    """イベント発表日のS&P500・ドル円・米10年債の日次変化を返す"""
    date_str = event.get('date', '')
    if not date_str or not daily_prices:
        return {}
    try:
        event_date = datetime.fromisoformat(date_str.replace('Z', '+00:00')).date()
        reactions  = {}
        for name, series in daily_prices.items():
            if series.empty:
                continue
            # インデックスを date に変換して比較
            idx_dates = [
                d.date() if hasattr(d, 'date') else pd.Timestamp(d).date()
                for d in series.index
            ]
            if event_date not in idx_dates:
                continue
            pos = idx_dates.index(event_date)
            if pos > 0:
                prev_close = float(series.iloc[pos - 1])
                curr_close = float(series.iloc[pos])
                pct = (curr_close - prev_close) / prev_close * 100
                reactions[name] = pct
        return reactions
    except Exception:
        return {}

# ── 市場の懸念ポイントをルールベースで自動生成 ──────────────
def generate_market_concerns(market_data, fred_rates, upcoming_events):
    concerns   = []
    ev_concerns = []

    us2    = fred_rates.get('米2年債利回り', {})
    us10   = market_data.get('米10年債利回り', {})
    vix    = market_data.get('VIX', {})
    sp500  = market_data.get('S&P500', {})
    dxy    = market_data.get('DXY', {})
    gold   = market_data.get('金', {})
    btc    = market_data.get('BTC', {})
    usdjpy = market_data.get('ドル円', {})

    # ── 1. イールドカーブ ──
    if us2.get('ok') and us10.get('ok'):
        spread = us10['value'] - us2['value']
        if spread < -0.2:
            concerns.append(
                f"⚠️【逆イールド {spread:+.2f}%】景気後退シグナル点灯中 → "
                f"CPI・PCE・雇用統計は「利下げ転換の根拠になるか」という観点で特に注目。"
            )
        elif spread < 0.3:
            concerns.append(
                f"➡️【フラットカーブ {spread:+.2f}%】方向感なし → "
                f"次の強いインフレor雇用データで金利方向が決まる可能性が大きい。"
            )

    # ── 2. VIX ──
    if vix.get('ok'):
        v = vix['value']
        if v >= 30:
            concerns.append(
                f"😰【VIX={v:.1f} パニック水準】全指標がリスクオフの引き金になりうる。"
                f"ネガティブサプライズに警戒。ポジション小さめ推奨。"
            )
        elif v >= 25:
            concerns.append(
                f"😟【VIX={v:.1f} 警戒水準】センチメント悪化中。"
                f"ポジティブサプライズでも反発が限定的な可能性がある。"
            )
        elif v < 15:
            concerns.append(
                f"😌【VIX={v:.1f} 極楽観】市場の安心感は高いが、"
                f"サプライズへの急反応リスクあり（ショートvol巻き戻し）。"
            )

    # ── 3. DXY トレンド ──
    if dxy.get('ok') and abs(dxy.get('pct', 0)) > 0.5:
        p = dxy['pct']
        if p > 0:
            concerns.append(
                f"💵【DXY +{p:.2f}% ドル高】新興国・コモディティ・BTC への売り圧力。"
                f"米金利上昇が続く場合は更に強まる。"
            )
        else:
            concerns.append(
                f"💵【DXY {p:.2f}% ドル安】リスク資産に追い風。"
                f"ただし米国の経済弱さが原因なら長続きしない可能性あり。"
            )

    # ── 4. S&P500 ──
    if sp500.get('ok'):
        p = sp500.get('pct', 0)
        if p < -2:
            concerns.append(
                f"📉【S&P500 {p:+.2f}%】リスクオフ加速中。"
                f"今週の指標は「景気悪化の確認」になるかどうかが焦点。"
            )
        elif p > 2:
            concerns.append(
                f"📈【S&P500 +{p:.2f}%】リスクオン継続。"
                f"強すぎる指標は「インフレ再燃→金利上昇→株売り」の逆回転リスクに注意。"
            )

    # ── 5. 金・BTC ──
    if gold.get('ok') and gold.get('pct', 0) > 1:
        concerns.append(
            f"🥇【金 +{gold['pct']:.2f}%】安全資産へ資金流入 → "
            f"地政学・インフレ・ドル不安のいずれかが高まっているサイン。"
        )
    if btc.get('ok') and btc.get('pct', 0) < -5:
        concerns.append(
            f"₿【BTC {btc['pct']:+.2f}%】急落 → "
            f"リスク資産全体への売り圧力。株式との連動に注意。"
        )

    # ── 6. ドル円 ──
    if usdjpy.get('ok'):
        p = usdjpy.get('pct', 0)
        if p > 0.5:
            concerns.append(
                f"円安【ドル円 +{p:.2f}%】進行 → "
                f"輸入コスト・日本の物価上昇圧力。日銀追加利上げ観測と交差するタイミング。"
            )
        elif p < -0.5:
            concerns.append(
                f"円高【ドル円 {p:.2f}%】進行 → "
                f"日本株への逆風。輸出企業の業績懸念。日銀政策と米金利の方向性が焦点。"
            )

    # ── 7. 今後の指標へのマッピング ──
    us_events = [e for e in upcoming_events if e.get('country') == 'US'][:6]
    jp_events = [e for e in upcoming_events if e.get('country') == 'JP'][:3]

    spread_val = (us10['value'] - us2['value']) if us2.get('ok') and us10.get('ok') else None
    vix_val    = vix['value'] if vix.get('ok') else None
    us2_val    = us2['value'] if us2.get('ok') else None

    for e in us_events + jp_events:
        title   = e.get('title', '')
        tl      = title.lower()
        country = e.get('country', '')
        dt_jst  = utc_to_jst_str(e.get('date', ''))
        est     = fmt_event_val(e.get('forecast'), e)
        prv     = fmt_event_val(e.get('previous'), e)
        prefix  = f"📊【{dt_jst}】[{country}] {title}（予想:{est} / 前回:{prv}）"

        if any(kw in tl for kw in ['cpi', 'consumer price', 'inflation', 'pce']):
            note = ''
            if spread_val is not None and spread_val < 0:
                note = f"逆イールド中（スプレッド{spread_val:+.2f}%）のため"
            elif us2_val:
                note = f"米2年金利{us2_val:.2f}%の中で"
            ev_concerns.append(
                f"{prefix} → {note}インフレ指標。"
                f"予想を上回ると「利下げ遠のく」として金利上昇・株安・ドル高の連鎖に注意。"
            )

        elif any(kw in tl for kw in ['nonfarm', 'non farm', 'payroll', 'unemployment', 'jobs added']):
            vix_note = f"（現在VIX={vix_val:.0f}）" if vix_val else ''
            ev_concerns.append(
                f"{prefix} → 雇用指標{vix_note}。"
                f"弱ければ「景気後退懸念→利下げ期待→株高」の単純図式が成り立つか、"
                f"それとも「景気悪化→株安」が勝るかが焦点。"
            )

        elif any(kw in tl for kw in ['pmi', 'ism manufacturing', 'ism services', 'business confidence']):
            ev_concerns.append(
                f"{prefix} → 景況感先行指標。"
                f"50割れ継続ならリセッション懸念強まる。株・為替ともに反応しやすい。"
            )

        elif any(kw in tl for kw in ['gdp', 'gross domestic']):
            ev_concerns.append(
                f"{prefix} → 景気サイクル確認。"
                f"前期比でどう変化したかが重要。弱ければ利下げ期待が高まりドル安要因。"
            )

        elif any(kw in tl for kw in ['fomc', 'interest rate decision', 'fed funds', 'rate decision']):
            ev_concerns.append(
                f"{prefix} → 最重要イベント。声明文のニュアンスと"
                f"ドットチャートの変化に注目。ドル円・株・金利すべてが大きく動く。"
            )

        elif any(kw in tl for kw in ['retail sales']):
            ev_concerns.append(
                f"{prefix} → 消費動向（米経済の7割は個人消費）。"
                f"弱ければ景気後退懸念を強化。強ければインフレ再燃リスク。"
            )

        elif any(kw in tl for kw in ['boj', 'bank of japan', 'tankan', '日銀']):
            ev_concerns.append(
                f"{prefix} → 日銀政策。追加利上げ観測がドル円の方向性に直結。"
                f"サプライズ利上げなら円高急進の可能性あり。"
            )

    return concerns + (ev_concerns if ev_concerns else [])

# ── テンプレート生成 ─────────────────────────────────────────
def build_template(market_data, fred_rates, news, user_news, cal_events):
    today   = datetime.now().strftime('%Y年%m月%d日')
    now_utc = datetime.now(timezone.utc)

    def v(k, src=None):
        return fmt_val((src or market_data).get(k, {}))

    def c(k, src=None):
        d = (src or market_data).get(k, {})
        if not d.get('ok'):
            return '前日比 不明'
        sign = '+' if d['pct'] >= 0 else ''
        return f"前日比 {sign}{d['pct']:.2f}%"

    vix_d   = market_data.get('VIX', {})
    vix_str = f"{v('VIX')}  {vix_status(vix_d)}"

    us2_d  = fred_rates.get('米2年債利回り', {})
    us10_d = market_data.get('米10年債利回り', {})
    us30_d = fred_rates.get('米30年債利回り', {})
    jp10_d = fred_rates.get('日本10年債利回り', {})
    _, curve_lbl = yield_curve_status(us2_d, us10_d)

    def rate_line(label, d, note=''):
        return f"・{label}：{fmt_val(d)}（前日比 {fmt_chg_bp(d)}）{note}"

    rates_text = "\n".join([
        rate_line('米2年債利回り',    us2_d),
        rate_line('米10年債利回り',   us10_d),
        rate_line('米30年債利回り',   us30_d),
        rate_line('日本10年債利回り', jp10_d, '（月次データ）'),
        f"・イールドカーブ（米2-10年スプレッド）：{curve_lbl or '不明'}",
    ])

    upcoming = [e for e in cal_events
                if e.get('date', '') > now_utc.strftime('%Y-%m-%dT%H:%M')
                and e.get('actual') is None]
    past_imp = [e for e in cal_events
                if e.get('actual') is not None
                and e.get('date', '') <= now_utc.strftime('%Y-%m-%dT%H:%M')]

    upcoming_lines = ''
    for e in sorted(upcoming, key=lambda x: x.get('date', ''))[:12]:
        est = fmt_event_val(e.get('forecast'), e)
        prv = fmt_event_val(e.get('previous'), e)
        upcoming_lines += (f"【{utc_to_jst_str(e['date'])} JST】"
                           f"[{e.get('country','')}] {e.get('title','')} "
                           f"予想:{est} / 前回:{prv}\n")

    past_lines = ''
    for e in sorted(past_imp, key=lambda x: x.get('date', ''), reverse=True)[:10]:
        act = fmt_event_val(e.get('actual'),   e)
        est = fmt_event_val(e.get('forecast'), e)
        prv = fmt_event_val(e.get('previous'), e)
        surprise = ''
        try:
            a_v = float(str(e.get('actual', '')))
            e_v = float(str(e.get('forecast', '')))
            surprise = ' ← 上振れ✅' if a_v > e_v else ' ← 下振れ⚠️'
        except Exception:
            pass
        past_lines += (f"【{utc_to_jst_str(e['date'])} JST】"
                       f"[{e.get('country','')}] {e.get('title','')} "
                       f"結果:{act}（予想:{est}{surprise}）/ 前回:{prv}\n")

    # 市場の懸念
    concerns = generate_market_concerns(market_data, fred_rates, upcoming)
    concerns_text = '\n'.join(f"・{c}" for c in concerns) if concerns else '（特筆すべき懸念なし）'

    news_lines = ''
    for n in news:
        news_lines += f"・{n['source']}: {n['title']}\n"
    if user_news.strip():
        news_lines += f"\n【Grok追加情報】\n{user_news.strip()}\n"

    return f"""【前置き・分析の文脈】

■ 私のトレード方針
BNFの「トータルの値動きへの洞察力が一番大事」という考え方を軸に、マクロ経済・地政学・気候などの出来事が、どの資産にどう波及するかを因果連鎖（風が吹けば桶屋が儲かる）で理解することを目標にしています。

■ 対象市場
日本株・米国株・仮想通貨（BTC等）・FX（ドル円中心）・コモディティ（原油・金・穀物等）・農産物市場など売買できるもの全て

■ 時間軸
数日〜数年（デイトレはしない。スイング〜長期）

■ 使っているフレームワーク
1. リスクオン/オフの大局
2. ドル高/安の連鎖（為替起点）
3. 実質金利の方向・良い/悪い利下げの区別
4. コモディティ（原油・穀物・金・銅）の連鎖
5. 気候・農業カレンダーの季節性
6. 地政学・関税・中央銀行イベントの連鎖
7. 主要通貨ペアの特性
8. トリガー→最終影響の早見パターン
9. 現在の相場サイクルの位置

■ 返答形式のお願い
・因果連鎖は「第1層→第2層→第3層」と階層で示してください
・天気予報形式（晴れ/曇り/雨/嵐）で全体感を示してください
・メインシナリオと、それが崩れる条件（リスクシナリオ）を分けてください
・専門用語には簡単な説明をつけてください（マクロ経済は初学者です）
・具体的な銘柄・通貨・商品名で示してください（抽象的な表現を避けてください）

■ 以下のデータ・ニュースを分析してください：

【日付】{today}

■ 為替
・ドル円：{v('ドル円')}（{c('ドル円')}）
・ユーロドル：{v('ユーロドル')}（{c('ユーロドル')}）
・ドルインデックス(DXY)：{v('DXY')}（{c('DXY')}）

■ 株式
・日経平均：{v('日経平均')}（{c('日経平均')}）
・S&P500：{v('S&P500')}（{c('S&P500')}）
・NASDAQ：{v('NASDAQ')}（{c('NASDAQ')}）
・上海総合：{v('上海総合')}（{c('上海総合')}）

■ コモディティ
・原油(WTI)：{v('原油(WTI)')}（{c('原油(WTI)')}）
・金：{v('金')}（{c('金')}）
・銅：{v('銅')}（{c('銅')}）

■ 債券・金利
{rates_text}

■ 仮想通貨
・BTC：{v('BTC')}（{c('BTC')}）
・ETH：{v('ETH')}（{c('ETH')}）

■ 恐怖指数
・VIX：{vix_str}

■ 主要ニュース
{news_lines}
■ 現在の市場環境から見た懸念ポイント（自動生成）
{concerns_text}

■ 今後10日間の注目経済指標
{upcoming_lines if upcoming_lines else '（取得できませんでした）'}
■ 直近7日間の指標発表と結果
{past_lines if past_lines else '（取得できませんでした）'}
---
【Claudeへの依頼】
1. 現在の相場環境（リスクオン/オフ・フェーズ）
2. 各ニュースの因果連鎖（風が吹けば桶屋が儲かる式）
3. 直近の指標発表（上振れ/下振れ）と市場の反応の考察
4. 上記の「懸念ポイント」を踏まえた今後10日間の注目指標の分析
5. 今日・今週動く可能性のある資産と方向
"""

# ── メインUI ────────────────────────────────────────────────
st.title("📊 相場チェッカー")
st.caption("市場データを自動取得してClaudeへのテンプレートを生成します")

if st.button("🔄 データを最新に更新", use_container_width=True, type="primary"):
    st.cache_data.clear()
    st.rerun()

st.caption(f"取得時刻：{datetime.now().strftime('%Y/%m/%d %H:%M')}")
st.divider()

with st.spinner("市場データ取得中..."):
    market_data = fetch_market_data()
with st.spinner("金利データ取得中 (FRED)..."):
    fred_rates = fetch_fred_rates()
with st.spinner("経済指標カレンダー取得中..."):
    cal_events = fetch_economic_calendar()
with st.spinner("市場反応データ取得中..."):
    daily_prices = fetch_daily_prices()

# ── 市場データ表示 ──────────────────────────────────────────
st.subheader("📈 市場データ")

sections = [
    ("🌏 為替",          ['ドル円', 'ユーロドル', 'DXY']),
    ("📊 株式",          ['日経平均', 'S&P500', 'NASDAQ', '上海総合']),
    ("🛢 コモディティ",  ['原油(WTI)', '金', '銅']),
    ("₿ 仮想通貨",      ['BTC', 'ETH']),
    ("📉 恐怖指数",      ['VIX']),
]

for sec_title, keys in sections:
    with st.expander(sec_title, expanded=True):
        rows = []
        for k in keys:
            d = market_data.get(k, {})
            row = {'銘柄': k, '現在値': fmt_val(d), '前日比': fmt_chg(d)}
            if k == 'VIX':
                row['状態'] = vix_status(d)
            rows.append(row)
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

# ── 金利・イールドカーブ ────────────────────────────────────
with st.expander("📐 債券・金利 / イールドカーブ", expanded=True):
    all_rates = {
        '米2年債利回り':    fred_rates.get('米2年債利回り',    {}),
        '米10年債利回り':   market_data.get('米10年債利回り',  {}),
        '米30年債利回り':   fred_rates.get('米30年債利回り',   {}),
        '日本10年債利回り': fred_rates.get('日本10年債利回り', {}),
    }
    rate_rows = []
    for name, d in all_rates.items():
        freq = d.get('freq', '') if d.get('ok') else ''
        rate_rows.append({
            '銘柄':     name,
            '現在値':   fmt_val(d),
            '変化':     fmt_chg_bp(d),
            '更新頻度': freq,
        })
    st.dataframe(pd.DataFrame(rate_rows), hide_index=True, use_container_width=True)

    us2_d  = fred_rates.get('米2年債利回り', {})
    us10_d = market_data.get('米10年債利回り', {})
    _, curve_lbl = yield_curve_status(us2_d, us10_d)
    if curve_lbl:
        st.info(f"イールドカーブ（米2-10年スプレッド）: {curve_lbl}")

st.divider()

# ── 市場の懸念ポイント ──────────────────────────────────────
st.subheader("🎯 市場の懸念ポイント（自動生成）")

now_utc  = datetime.now(timezone.utc)
upcoming = [e for e in cal_events
            if e.get('date', '') > now_utc.strftime('%Y-%m-%dT%H:%M')
            and e.get('actual') is None]
past_imp = [e for e in cal_events
            if e.get('actual') is not None
            and e.get('date', '') <= now_utc.strftime('%Y-%m-%dT%H:%M')]

concerns = generate_market_concerns(market_data, fred_rates, upcoming)

with st.expander(f"⚠️ 現在の市場環境と今後の注目ポイント（{len(concerns)}件）", expanded=True):
    if concerns:
        for c in concerns:
            st.markdown(f"- {c}")
    else:
        st.info("現時点で特筆すべき懸念ポイントはありません")

st.divider()

# ── 経済指標カレンダー ──────────────────────────────────────
st.subheader("📅 経済指標カレンダー")

with st.expander(f"📌 今後の注目指標（{len(upcoming)}件）", expanded=True):
    if upcoming:
        up_rows = []
        for e in sorted(upcoming, key=lambda x: x.get('date', ''))[:20]:
            up_rows.append({
                '日時(JST)': utc_to_jst_str(e.get('date', '')),
                '国':        e.get('country', ''),
                '指標':      e.get('title', ''),
                '予想':      fmt_event_val(e.get('forecast'), e),
                '前回':      fmt_event_val(e.get('previous'), e),
            })
        st.dataframe(pd.DataFrame(up_rows), hide_index=True, use_container_width=True)
    else:
        st.info("カレンダーデータを取得できませんでした")

with st.expander(f"🔍 直近の指標と結果・市場反応（{len(past_imp)}件）", expanded=True):
    if past_imp:
        past_rows = []
        for e in sorted(past_imp, key=lambda x: x.get('date', ''), reverse=True)[:20]:
            act = fmt_event_val(e.get('actual'),   e)
            est = fmt_event_val(e.get('forecast'), e)
            prv = fmt_event_val(e.get('previous'), e)
            surprise = ''
            try:
                a_v = float(str(e.get('actual', '')))
                e_v = float(str(e.get('forecast', '')))
                surprise = '✅ 上振れ' if a_v > e_v else '⚠️ 下振れ'
            except Exception:
                pass

            # 市場反応の計算
            reaction = get_event_reaction(e, daily_prices)
            sp_chg  = fmt_pct(reaction.get('S&P500'))
            usd_chg = fmt_pct(reaction.get('ドル円'))

            past_rows.append({
                '日時(JST)':   utc_to_jst_str(e.get('date', '')),
                '国':          e.get('country', ''),
                '指標':        e.get('title', ''),
                '結果':        act,
                '予想':        est,
                'vs予想':      surprise,
                'S&P500反応':  sp_chg,
                'ドル円反応':  usd_chg,
            })
        st.dataframe(pd.DataFrame(past_rows), hide_index=True, use_container_width=True)
        st.caption("※ 市場反応は発表日の日次終値ベース（発表時刻と市場の取引時間によりズレあり）")
    else:
        st.info("直近の発表データが取得できませんでした")

st.divider()

# ── ニュース ────────────────────────────────────────────────
st.subheader("📰 ニュース（自動取得）")

with st.spinner("ニュース取得中..."):
    auto_news = fetch_news()

if auto_news:
    for n in auto_news:
        st.markdown(f"- **{n['source']}**：{n['title']}")
else:
    st.info("ニュースを取得できませんでした（ネットワーク確認）")

st.divider()

# ── Grok追加ニュース ────────────────────────────────────────
st.subheader("✏️ Grokから追加ニュース（任意）")
user_news = st.text_area(
    "Grokのニュース要約をここに貼り付けてください",
    placeholder="例：FRB議長が〇〇と発言...\nトランプ大統領が関税を〇〇...",
    height=120,
    label_visibility="collapsed"
)

st.divider()

# ── テンプレート生成 ─────────────────────────────────────────
st.subheader("📋 Claudeへのテンプレート生成")

if st.button("📝 テンプレートを生成する", use_container_width=True, type="primary"):
    template = build_template(market_data, fred_rates, auto_news, user_news, cal_events)
    st.success("✅ 生成完了！下のテキストをコピーしてClaudeに貼り付けてください")
    st.code(template, language=None)
    st.info("💡 コードブロック右上の 📋 アイコンでコピーできます（スマホは長押し→全選択→コピー）")

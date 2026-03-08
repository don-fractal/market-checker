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

# ── FRED series: 米2年・30年・日本10年（月次）──────────────
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
■ 今後10日間の注目経済指標（重要度★★★）
{upcoming_lines if upcoming_lines else '（取得できませんでした）'}
■ 直近7日間の指標発表と結果
{past_lines if past_lines else '（取得できませんでした）'}
---
【Claudeへの依頼】
1. 現在の相場環境（リスクオン/オフ・フェーズ）
2. 各ニュースの因果連鎖（風が吹けば桶屋が儲かる式）
3. 直近の指標発表（上振れ/下振れ）と市場の反応の考察
4. 今後10日間の注目指標について、現在の市場環境から見た「市場の懸念・注目ポイント」
   例）「先行指標がインフレ示唆だが利回りはまだ上昇していない → 今回のCPIは重要」など
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

# ── 経済指標カレンダー ──────────────────────────────────────
st.subheader("📅 経済指標カレンダー")

now_utc  = datetime.now(timezone.utc)
upcoming = [e for e in cal_events
            if e.get('date', '') > now_utc.strftime('%Y-%m-%dT%H:%M')
            and e.get('actual') is None]
past_imp = [e for e in cal_events
            if e.get('actual') is not None
            and e.get('date', '') <= now_utc.strftime('%Y-%m-%dT%H:%M')]

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

with st.expander(f"🔍 直近の指標と結果（{len(past_imp)}件）", expanded=True):
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
            past_rows.append({
                '日時(JST)': utc_to_jst_str(e.get('date', '')),
                '国':        e.get('country', ''),
                '指標':      e.get('title', ''),
                '結果':      act,
                '予想':      est,
                '前回':      prv,
                'vs予想':    surprise,
            })
        st.dataframe(pd.DataFrame(past_rows), hide_index=True, use_container_width=True)
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

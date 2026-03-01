import streamlit as st
import yfinance as yf
import feedparser
from datetime import datetime
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

# ── 取得する銘柄定義 ────────────────────────────────────────
TICKERS = {
    'ドル円':        ('USDJPY=X',   '円'),
    'ユーロドル':    ('EURUSD=X',   ''),
    'DXY':           ('DX-Y.NYB',   ''),
    '日経平均':      ('^N225',      '円'),
    'S&P500':        ('^GSPC',      ''),
    'NASDAQ':        ('^IXIC',      ''),
    '上海総合':      ('000001.SS',  ''),
    '原油(WTI)':    ('CL=F',       '$'),
    '金':            ('GC=F',       '$'),
    '銅':            ('HG=F',       '$'),
    '米10年債利回り':  ('^TNX',    '%'),
    'BTC':           ('BTC-USD',    '$'),
    'ETH':           ('ETH-USD',    '$'),
    'VIX':           ('^VIX',       ''),
}

NEWS_FEEDS = [
    ('Reuters',  'https://feeds.reuters.com/reuters/businessNews'),
    ('NHK経済',  'https://www3.nhk.or.jp/rss/news/cat6.xml'),
]

# ── データ取得（5分キャッシュ） ─────────────────────────────
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

def vix_status(d):
    if not d.get('ok') or d['value'] is None:
        return ''
    v = d['value']
    if v < 15:  return '😌 極平穏'
    if v < 20:  return '😊 平穏'
    if v < 25:  return '😐 要注意'
    if v < 30:  return '😟 警戒'
    return '😰 要警戒'

# ── テンプレート生成 ─────────────────────────────────────────
def build_template(data, news, user_news):
    today = datetime.now().strftime('%Y年%m月%d日')

    def v(k):
        return fmt_val(data.get(k, {}))

    def c(k):
        d = data.get(k, {})
        if not d.get('ok'):
            return '昨日比 不明'
        sign = '+' if d['pct'] >= 0 else ''
        return f"昨日比 {sign}{d['pct']:.2f}%"

    vix_d   = data.get('VIX', {})
    vix_str = f"{v('VIX')}  {vix_status(vix_d)}"

    news_lines = ''
    for n in news:
        news_lines += f"・{n['source']}: {n['title']}\n"
    if user_news.strip():
        news_lines += f"\n【Grok追加情報】\n{user_news.strip()}\n"

    return f"""【前置き】
私はBNFの「トータルの値動き」の考え方を学びながら、マクロ経済の因果連鎖でトレードの判断を補助してもらいたいと考えています。

分析の際は以下の観点でお願いします：
・対象：日本株・米国株・仮想通貨・FX・コモディティ・農産物など全市場
・時間軸：数日〜数年（複数の時間軸を意識）
・返答形式：「風が吹けば桶屋が儲かる」式の因果連鎖で、原因→中間経路→最終的に動く資産・銘柄の順で説明してください
・知識レベル：マクロ経済の初学者です。専門用語は都度説明をつけてください

以下のデータ・ニュースを分析してください：

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
・米10年国債利回り：{v('米10年債利回り')}（{c('米10年債利回り')}）
・日本10年国債利回り：（要手動確認）

■ 仮想通貨
・BTC：{v('BTC')}（{c('BTC')}）
・ETH：{v('ETH')}（{c('ETH')}）

■ 恐怖指数
・VIX：{vix_str}

■ 主要ニュース
{news_lines}
---
【Claudeへの依頼】
1. 現在の相場環境（リスクオン/オフ・フェーズ）
2. 各ニュースの因果連鎖（風が吹けば桶屋が儲かる）
3. 今後数日の注目ポイントと分岐条件
4. 今日・今週動く可能性のある資産と方向
"""

# ── メインUI ────────────────────────────────────────────────
st.title("📊 相場チェッカー")
st.caption("市場データを自動取得してClaudeへのテンプレートを生成します")

# データ更新ボタン
if st.button("🔄 データを最新に更新", use_container_width=True, type="primary"):
    st.cache_data.clear()
    st.rerun()

st.caption(f"取得時刻：{datetime.now().strftime('%Y/%m/%d %H:%M')}")
st.divider()

# データ取得
with st.spinner("市場データ取得中..."):
    market_data = fetch_market_data()

# ── 市場データ表示 ──────────────────────────────────────────
st.subheader("📈 市場データ")

sections = [
    ("🌏 為替",          ['ドル円', 'ユーロドル', 'DXY']),
    ("📊 株式",          ['日経平均', 'S&P500', 'NASDAQ', '上海総合']),
    ("🛢 コモディティ",  ['原油(WTI)', '金', '銅']),
    ("₿ 仮想通貨",      ['BTC', 'ETH']),
    ("📉 金利・恐怖指数", ['米10年債利回り', 'VIX']),
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
        df = pd.DataFrame(rows)
        st.dataframe(df, hide_index=True, use_container_width=True)

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
    template = build_template(market_data, auto_news, user_news)
    st.success("✅ 生成完了！下のテキストをコピーしてClaudeに貼り付けてください")
    st.code(template, language=None)
    st.info("💡 コードブロック右上の 📋 アイコンでコピーできます（スマホは長押し→全選択→コピー）")

"""
generate_report.py
Generates a PDF report for the Thong Yip Thong Yod project:
  - Literature Review
  - Relevant Theories & Proposed Methods
  - Data Preprocessing
  - Data Analysis
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_JUSTIFY
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

OUTPUT = os.path.join(os.path.dirname(__file__), "Thong_Yip_Thong_Yod_Report.pdf")

# ── Colours ───────────────────────────────────────────────────────────────────
GOLD      = colors.HexColor("#C9A84C")
DARK      = colors.HexColor("#1A1A1A")
MID       = colors.HexColor("#444444")
LIGHT     = colors.HexColor("#F5F5F5")
ACCENT    = colors.HexColor("#2E4057")
WHITE     = colors.white
TABLE_HDR = colors.HexColor("#2E4057")
TABLE_ROW = colors.HexColor("#F9F9F9")
TABLE_ALT = colors.HexColor("#FFFFFF")
HR_COLOR  = colors.HexColor("#C9A84C")

# ── Styles ────────────────────────────────────────────────────────────────────
def make_styles():
    base = getSampleStyleSheet()

    styles = {}

    styles["cover_title"] = ParagraphStyle(
        "cover_title", fontSize=26, leading=32, textColor=GOLD,
        alignment=TA_CENTER, fontName="Helvetica-Bold", spaceAfter=6,
    )
    styles["cover_sub"] = ParagraphStyle(
        "cover_sub", fontSize=13, leading=18, textColor=WHITE,
        alignment=TA_CENTER, fontName="Helvetica", spaceAfter=4,
    )
    styles["cover_meta"] = ParagraphStyle(
        "cover_meta", fontSize=10, leading=14, textColor=colors.HexColor("#AAAAAA"),
        alignment=TA_CENTER, fontName="Helvetica",
    )

    styles["h1"] = ParagraphStyle(
        "h1", fontSize=16, leading=22, textColor=ACCENT,
        fontName="Helvetica-Bold", spaceBefore=18, spaceAfter=6,
        borderPad=4,
    )
    styles["h2"] = ParagraphStyle(
        "h2", fontSize=13, leading=18, textColor=ACCENT,
        fontName="Helvetica-Bold", spaceBefore=14, spaceAfter=4,
    )
    styles["h3"] = ParagraphStyle(
        "h3", fontSize=11, leading=16, textColor=MID,
        fontName="Helvetica-Bold", spaceBefore=10, spaceAfter=3,
    )
    styles["body"] = ParagraphStyle(
        "body", fontSize=10, leading=15, textColor=DARK,
        fontName="Helvetica", spaceBefore=2, spaceAfter=4,
        alignment=TA_JUSTIFY,
    )
    styles["bullet"] = ParagraphStyle(
        "bullet", fontSize=10, leading=15, textColor=DARK,
        fontName="Helvetica", leftIndent=16, spaceBefore=1, spaceAfter=2,
        bulletIndent=6,
    )
    styles["code"] = ParagraphStyle(
        "code", fontSize=8.5, leading=13, textColor=colors.HexColor("#2B2B2B"),
        fontName="Courier", backColor=colors.HexColor("#F4F4F4"),
        leftIndent=12, rightIndent=12, spaceBefore=4, spaceAfter=6,
        borderColor=colors.HexColor("#DDDDDD"), borderWidth=0.5,
        borderPad=6, borderRadius=3,
    )
    styles["formula"] = ParagraphStyle(
        "formula", fontSize=10, leading=15, textColor=ACCENT,
        fontName="Courier-Bold", alignment=TA_CENTER,
        spaceBefore=4, spaceAfter=6,
    )
    styles["caption"] = ParagraphStyle(
        "caption", fontSize=8, leading=12, textColor=MID,
        fontName="Helvetica-Oblique", alignment=TA_CENTER, spaceAfter=6,
    )

    return styles

S = make_styles()


def hr():
    return HRFlowable(width="100%", thickness=0.8, color=HR_COLOR, spaceAfter=6, spaceBefore=6)


def h1(text):
    return Paragraph(text, S["h1"])

def h2(text):
    return Paragraph(text, S["h2"])

def h3(text):
    return Paragraph(text, S["h3"])

def body(text):
    return Paragraph(text, S["body"])

def bullet(text):
    return Paragraph(f"• &nbsp; {text}", S["bullet"])

def code(text):
    # escape angle brackets
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(text, S["code"])

def formula(text):
    text = text.replace("<", "&lt;").replace(">", "&gt;")
    return Paragraph(text, S["formula"])

def sp(n=6):
    return Spacer(1, n)


def make_table(header_row, data_rows, col_widths=None):
    all_rows = [header_row] + data_rows
    t = Table(all_rows, colWidths=col_widths, repeatRows=1)
    style = TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  TABLE_HDR),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  WHITE),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0),  9),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 7),
        ("TOPPADDING",    (0, 0), (-1, 0), 7),
        ("FONTNAME",    (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE",    (0, 1), (-1, -1), 9),
        ("TOPPADDING",    (0, 1), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [TABLE_ROW, TABLE_ALT]),
        ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
        ("ALIGN",       (0, 0), (-1, -1), "LEFT"),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
    ])
    t.setStyle(style)
    return t


# ── Cover Page ────────────────────────────────────────────────────────────────
def cover_page():
    items = []
    items.append(Spacer(1, 3.5 * cm))

    # Gold bar decoration
    items.append(HRFlowable(width="60%", thickness=3, color=GOLD,
                             spaceAfter=16, hAlign="CENTER"))

    items.append(Paragraph("🥇 Thong Yip Thong Yod", S["cover_title"]))
    items.append(sp(4))
    items.append(Paragraph("AI-Powered Gold Trading Agent", ParagraphStyle(
        "ct2", fontSize=14, leading=20, textColor=WHITE,
        alignment=TA_CENTER, fontName="Helvetica-Bold")))
    items.append(sp(8))

    items.append(HRFlowable(width="40%", thickness=1, color=GOLD,
                             spaceAfter=16, hAlign="CENTER"))
    items.append(sp(8))

    items.append(Paragraph("Research Report", S["cover_sub"]))
    items.append(sp(4))
    items.append(Paragraph(
        "Literature Review · Relevant Theories &amp; Proposed Methods<br/>"
        "Data Preprocessing · Data Analysis",
        S["cover_sub"]))

    items.append(Spacer(1, 2.5 * cm))
    items.append(HRFlowable(width="40%", thickness=0.5,
                             color=colors.HexColor("#555555"),
                             spaceAfter=12, hAlign="CENTER"))

    items.append(Paragraph("Thammasat University — Data Science Project", S["cover_meta"]))
    items.append(sp(4))
    items.append(Paragraph("Team 3 &nbsp;|&nbsp; Branch: Team3", S["cover_meta"]))
    items.append(sp(4))
    items.append(Paragraph("Stack: Python · Claude API · Gradio · MongoDB Atlas", S["cover_meta"]))
    items.append(sp(4))
    items.append(Paragraph("Date: March 30, 2026", S["cover_meta"]))

    items.append(HRFlowable(width="60%", thickness=3, color=GOLD,
                             spaceBefore=24, hAlign="CENTER"))
    items.append(PageBreak())
    return items


# ── Section 1: Literature Review ─────────────────────────────────────────────
def section_literature():
    items = []
    items.append(h1("1.  LITERATURE REVIEW"))
    items.append(hr())

    # 1.1
    items.append(h2("1.1  AI-Powered Trading Systems"))
    items.append(body(
        "Research into algorithmic trading has evolved significantly since the 1990s. "
        "<b>Brock et al. (1992)</b> demonstrated that technical indicators such as Moving Average "
        "and Trading Range Breakout strategies could generate returns superior to buy-and-hold "
        "on the Dow Jones Industrial Average. <b>Lo et al. (2000)</b> subsequently confirmed "
        "that statistically significant pattern recognition is possible in financial time series."
    ))
    items.append(body(
        "In the era of Large Language Models, <b>Lopez-Lira &amp; Tang (2023)</b> found that "
        "ChatGPT sentiment scores derived from financial news are positively correlated with "
        "next-day stock returns, particularly among retail-investor-heavy equities. "
        "<b>Koa et al. (2024)</b> extended this work by proposing a framework using LLMs as "
        "reasoning engines within a trading system via the <b>ReAct paradigm (Yao et al., 2022)</b>."
    ))

    # 1.2
    items.append(h2("1.2  Gold Market Dynamics"))
    items.append(body(
        "Gold possesses unique characteristics as a safe-haven asset with an inverse relationship "
        "to the US Dollar Index (<b>Baur &amp; Lucey, 2010</b>). <b>Capie et al. (2005)</b> demonstrated "
        "that gold effectively hedges geopolitical risk. In the Thai context, gold bullion prices "
        "are pegged to XAUUSD via the USD/THB exchange rate and the 96.5% purity standard "
        "established by the Gold Traders Association of Thailand."
    ))

    # 1.3
    items.append(h2("1.3  Technical Analysis as Feature Engineering"))
    items.append(body(
        "<b>Murphy (1999)</b> established that RSI and MACD are among the most effective indicators "
        "for momentum trading. <b>Bollinger (2002)</b> introduced Bollinger Bands as a method "
        "to simultaneously measure relative price level and volatility. "
        "<b>Sezer et al. (2020)</b>, in a comprehensive review of deep learning applied to financial "
        "time series, concluded that combining multiple technical indicators with news sentiment "
        "consistently outperforms any single indicator in isolation."
    ))

    # 1.4
    items.append(h2("1.4  Knowledge Graphs in Finance"))
    items.append(body(
        "<b>LightRAG (Edge et al., 2024)</b> proposes a graph-based retrieval-augmented generation "
        "approach that scales better than traditional RAG through entity-relationship-aware "
        "retrieval. This is particularly suited to the financial domain where entities such as "
        "the Federal Reserve, the US Dollar, and Gold exhibit complex temporal relationships."
    ))

    # 1.5
    items.append(h2("1.5  Risk Management in Algorithmic Trading"))
    items.append(body(
        "<b>Kelly (1956)</b> derived the Kelly Criterion for optimal position sizing in repeated "
        "bets. <b>Thorp (2006)</b> recommended using Half-Kelly in practice to reduce variance. "
        "<b>Sharpe (1966)</b> introduced the risk-adjusted return ratio bearing his name, while "
        "<b>Sortino &amp; van der Meer (1991)</b> refined this by penalising only downside volatility — "
        "both metrics are now industry standard for evaluating trading system performance."
    ))

    items.append(PageBreak())
    return items


# ── Section 2: Theories & Methods ────────────────────────────────────────────
def section_methods():
    items = []
    items.append(h1("2.  RELEVANT THEORIES &amp; PROPOSED METHODS"))
    items.append(hr())

    # 2.1 ReAct
    items.append(h2("2.1  ReAct Framework (Reasoning + Acting)"))
    items.append(body(
        "This project adopts the <b>ReAct paradigm (Yao et al., 2022)</b>, which interleaves "
        "reasoning steps with action calls in a structured loop. The agent alternates between "
        "thinking and calling tools until it accumulates sufficient evidence to produce a final "
        "BUY / SELL / HOLD decision with confidence percentage."
    ))
    items.append(sp(4))
    items.append(code(
        "Thought  → Analyse available data\n"
        "Action   → Call tool  (get_price | get_indicators | get_news)\n"
        "Observe  → Receive tool result\n"
        "Thought  → Continue reasoning from new data\n"
        "  ...\n"
        "Answer   → BUY / SELL / HOLD  +  confidence %"
    ))
    items.append(body("<b>Advantages of ReAct over single-prompt design:</b>"))
    for b in [
        "Agent selects required data autonomously — no hardcoded pipeline",
        "Multi-step chain reasoning across tool calls",
        "Fully interpretable — entire thought process is visible",
        "Reduced hallucination — grounded in real-time data",
    ]:
        items.append(bullet(b))

    # 2.2 Multi-Agent
    items.append(h2("2.2  Multi-Agent Architecture"))
    items.append(body(
        "Responsibilities are divided across two agents operating on different time horizons "
        "to balance cost and freshness:"
    ))
    items.append(sp(4))
    items.append(code(
        "Daily Market Agent  (Claude Haiku)   ← macro trend — runs once per day\n"
        "        ↓  inject into get_indicators result\n"
        "Main ReAct Agent    (Claude Sonnet)  ← micro decision — runs every 5 min"
    ))
    items.append(make_table(
        ["Layer", "Model", "Frequency", "Responsibility"],
        [
            ["Macro", "Claude Haiku", "1× / day", "30-day trend → Uptrend / Downtrend / Sideways"],
            ["Micro", "Claude Sonnet", "1× / 5 min", "Indicators + news → BUY / SELL / HOLD"],
        ],
        col_widths=[2.5*cm, 3.5*cm, 3*cm, 8*cm]
    ))

    # 2.3 Pre-Computed Scoring
    items.append(h2("2.3  Pre-Computed Signal Scoring"))
    items.append(body(
        "Rather than allowing Claude to recalculate indicators (which introduces numerical "
        "errors), the system pre-computes all values deterministically and injects them as "
        "structured JSON into the agent context. Claude acts as a <b>reasoner</b>, not a calculator."
    ))
    items.append(sp(4))
    items.append(code(
        'pre_scored_signals = {\n'
        '    "buy_score":  "2 / 5",   # RSI oversold, MACD bullish\n'
        '    "sell_score": "3 / 5",   # BB overbought, daily trend down\n'
        '    "net_signal": "BEARISH",\n'
        '    "confluence": 3.8        # 0–10 scale\n'
        '}'
    ))

    # 2.4 Confidence Gate + Risk
    items.append(h2("2.4  Confidence Gate &amp; Risk Management Rules"))
    items.append(body(
        "A confidence threshold prevents low-conviction trades. Automated TP/SL guards protect "
        "open positions independently of Claude's next decision."
    ))
    items.append(sp(4))
    items.append(code(
        "Confidence >= 65%  →  execute trade\n"
        "Confidence <  65%  →  skip (HOLD)\n\n"
        "Take Profit  +1.5% →  auto SELL (lock profit)\n"
        "Stop Loss    -1.0% →  auto SELL (cut loss)\n"
        "Cooldown  2 rounds →  pause after close (prevent overtrading)"
    ))

    # 2.5 Kelly
    items.append(h2("2.5  Kelly Criterion for LLM Agents"))
    items.append(body(
        "Because LLMs exhibit a tendency toward overconfidence in signal quality estimates, "
        "the system uses <b>Half-Kelly</b> for position sizing rather than the Full Kelly fraction."
    ))
    items.append(formula("f* = W  -  (1 - W) / R         [Full Kelly]"))
    items.append(formula("f_half = f* / 2                 [Half-Kelly — used in production]"))
    items.append(body(
        "Example: Win rate W = 55%, Reward ratio R = 1.5  →  "
        "Full Kelly = 18.3%  →  Half-Kelly = 9.2% of portfolio"
    ))

    items.append(PageBreak())
    return items


# ── Section 3: Data Preprocessing ────────────────────────────────────────────
def section_preprocessing():
    items = []
    items.append(h1("3.  DATA PREPROCESSING"))
    items.append(hr())

    # 3.1 Data sources
    items.append(h2("3.1  Data Sources"))
    items.append(make_table(
        ["Data", "Source", "Frequency", "Library"],
        [
            ["OHLCV Gold Price", "Yahoo Finance (GC=F)", "Daily / 1-hour", "yfinance"],
            ["USD/THB Rate", "Yahoo Finance (THB=X)", "Real-time", "yfinance"],
            ["Gold News Headlines", "NewsAPI.org", "On-demand", "requests"],
        ],
        col_widths=[4.5*cm, 5*cm, 3.5*cm, 4*cm]
    ))
    items.append(sp(6))
    items.append(code(
        "# Fetch last 90 days of daily OHLCV data\n"
        'df = yf.download("GC=F", period="90d", interval="1d", auto_adjust=True)'
    ))

    # 3.2 Cleaning
    items.append(h2("3.2  Data Cleaning"))
    items.append(h3("Step 1 — Remove Missing Values"))
    items.append(code(
        "df = df.dropna(subset=['Close'])\n"
        "# Removes rows where Close is NaN (market holidays, halts)"
    ))
    items.append(h3("Step 2 — Minimum Row Validation"))
    for b in [
        "≥ 14 rows required for RSI(14)",
        "≥ 26 rows required for MACD(12, 26, 9)",
        "≥ 20 rows required for Bollinger Bands(20)",
    ]:
        items.append(bullet(b))

    items.append(h3("Step 3 — Timezone Normalisation"))
    items.append(code(
        "# All timestamps converted to Thai time (UTC+7) before display\n"
        "THAI_TZ = timezone(timedelta(hours=7))\n"
        "timestamp = datetime.now(THAI_TZ).strftime('%Y-%m-%d %H:%M')"
    ))
    items.append(h3("Step 4 — MultiIndex Column Handling"))
    items.append(code(
        "# yfinance may return MultiIndex columns\n"
        "if isinstance(df.columns, pd.MultiIndex):\n"
        "    df.columns = df.columns.get_level_values(0)"
    ))

    # 3.3 Feature Engineering
    items.append(h2("3.3  Feature Engineering — Technical Indicators"))

    items.append(h3("RSI — Wilder's Smoothing Method"))
    items.append(formula("RSI = 100 - 100 / (1 + RS)"))
    items.append(formula("RS = SMMA(Gains, 14) / SMMA(Losses, 14)"))
    items.append(body(
        "Wilder's Smoothed Moving Average (SMMA) is implemented as an Exponentially "
        "Weighted Moving Average with α = 1/period and adjust=False, which is "
        "mathematically equivalent to the original Wilder definition."
    ))
    items.append(code(
        "avg_gain = gain.ewm(alpha=1/14, min_periods=14, adjust=False).mean()\n"
        "avg_loss = loss.ewm(alpha=1/14, min_periods=14, adjust=False).mean()"
    ))

    items.append(h3("MACD — Moving Average Convergence Divergence"))
    items.append(formula("MACD = EMA(12) - EMA(26)"))
    items.append(formula("Signal = EMA(MACD, 9)"))
    items.append(formula("Histogram = MACD - Signal"))

    items.append(h3("Bollinger Bands"))
    items.append(formula("Upper = SMA(20) + 2 * StdDev(20)"))
    items.append(formula("Lower = SMA(20) - 2 * StdDev(20)"))
    items.append(formula("%B = (Close - Lower) / (Upper - Lower)"))

    # 3.4 Price Conversion
    items.append(h2("3.4  Price Conversion — USD/oz → THB/Baht-Weight"))
    items.append(body(
        "Gold prices from Yahoo Finance are quoted in USD per troy ounce (XAUUSD). "
        "The system converts to Thai Baht per baht-weight using the 96.5% purity "
        "standard of the Gold Traders Association of Thailand."
    ))
    items.append(formula(
        "P(THB/bw) = P(USD/oz) × R(USD/THB) / 31.1035 × 15.244 × 0.965"
    ))
    items.append(make_table(
        ["Constant", "Value", "Meaning"],
        [
            ["Troy Ounce", "31.1035 g", "International standard"],
            ["Baht Weight", "15.244 g", "Thai gold standard"],
            ["Purity", "0.965 (96.5%)", "Gold Traders Association of Thailand"],
        ],
        col_widths=[5*cm, 4*cm, 8*cm]
    ))

    # 3.5 News Preprocessing
    items.append(h2("3.5  News Sentiment Preprocessing"))
    items.append(code(
        "Raw news (NewsAPI)\n"
        "    ↓  Extract 'title' field only\n"
        "    ↓  Filter '[Removed]' and empty strings\n"
        "    ↓  Send to Claude Haiku for sentiment scoring\n"
        "    ↓  BULLISH / BEARISH / NEUTRAL\n"
        "    ↓  Cache result for 10 minutes (MD5 hash of headlines)"
    ))

    items.append(PageBreak())
    return items


# ── Section 4: Data Analysis ──────────────────────────────────────────────────
def section_analysis():
    items = []
    items.append(h1("4.  DATA ANALYSIS"))
    items.append(hr())

    # 4.1 Signal Analysis
    items.append(h2("4.1  Technical Signal Analysis — Multi-Indicator Confluence"))
    items.append(body(
        "The system evaluates multiple indicators simultaneously and combines them into "
        "a single Confluence Score. No single indicator triggers a trade in isolation."
    ))
    items.append(sp(4))
    items.append(make_table(
        ["Indicator", "Condition", "Signal", "Score"],
        [
            ["RSI", "< 30  (Oversold zone)", "BUY", "+2.0"],
            ["RSI", "< 40  (Approaching oversold)", "BUY", "+1.0"],
            ["RSI", "> 60  (Approaching overbought)", "SELL", "-1.0"],
            ["RSI", "> 70  (Overbought zone)", "SELL", "-2.0"],
            ["MACD Histogram", "> 0  (Bullish momentum)", "BUY", "+1.5"],
            ["MACD Histogram", "< 0  (Bearish momentum)", "SELL", "-1.5"],
            ["BB %B", "< 0.30  (Price near lower band)", "BUY", "+1.5"],
            ["BB %B", "> 0.70  (Price near upper band)", "SELL", "-1.5"],
            ["News Sentiment", "BULLISH", "BUY", "+1.5"],
            ["News Sentiment", "BEARISH", "SELL", "-1.5"],
        ],
        col_widths=[3.5*cm, 6.5*cm, 2.5*cm, 2*cm]
    ))
    items.append(sp(6))
    items.append(formula("Confluence Score = (raw_sum + 6.5) / 13.0 × 10.0"))
    items.append(body("Raw range: [-6.5, +6.5] → mapped linearly to [0, 10]"))

    # 4.2 Market Regime
    items.append(h2("4.2  Market Regime Detection"))
    items.append(body(
        "The market regime classifier categorises current conditions to provide context "
        "for the agent's decision. Rules are evaluated in priority order:"
    ))
    items.append(make_table(
        ["Regime", "Condition", "Trading Implication"],
        [
            ["VOLATILE",      "BB Bandwidth > 0.04",                    "High risk — avoid new entries"],
            ["TRENDING UP",   "MACD Hist > 0 AND Price > SMA(20)",       "Favour BUY signals"],
            ["TRENDING DOWN", "MACD Hist < 0 AND Price < SMA(20)",       "Favour SELL signals"],
            ["RANGING",       "None of the above",                       "Neutral — wait for breakout"],
        ],
        col_widths=[3.5*cm, 7*cm, 6.5*cm]
    ))

    # 4.3 Risk Metrics
    items.append(h2("4.3  Risk Metrics Analysis"))

    items.append(h3("Sharpe Ratio — Risk-Adjusted Return"))
    items.append(formula("S = E[Rp - Rf] / StdDev(Rp - Rf)  ×  sqrt(252)"))
    items.append(make_table(
        ["Sharpe Value", "Interpretation"],
        [
            ["≥ 2.0", "Excellent"],
            ["≥ 1.0", "Good"],
            ["≥ 0.5", "Acceptable"],
            ["< 0.5",  "Poor"],
        ],
        col_widths=[5*cm, 12*cm]
    ))

    items.append(h3("Sortino Ratio — Downside Risk Only"))
    items.append(formula("Sortino = E[Rp - τ] / sqrt(E[min(0, Rp - τ)²])  ×  sqrt(252)"))
    items.append(body(
        "Unlike Sharpe, Sortino penalises only downside volatility — "
        "upside variance is not penalised. This is more appropriate for "
        "asymmetric return distributions common in gold markets."
    ))

    items.append(h3("Maximum Drawdown"))
    items.append(formula("MDD = max_t [ (max_{τ≤t} V_τ  -  V_t) / max_{τ≤t} V_τ ]"))
    items.append(body("Expressed as a negative fraction, e.g. -0.18 = 18% peak-to-trough loss."))

    items.append(h3("Expected Value (EV)"))
    items.append(formula("EV = (W × R_W)  -  (L × R_L)"))
    items.append(body(
        "A positive EV indicates the strategy is mathematically profitable over a large "
        "number of trades. Even a sub-50% win rate can yield positive EV if the reward "
        "ratio R_W / R_L is sufficiently large (e.g. win rate 40%, RR = 2.5 → EV > 0)."
    ))

    items.append(h3("Live Performance Example (March 30, 2026)"))
    items.append(make_table(
        ["Metric", "Value", "Interpretation"],
        [
            ["Sharpe Ratio",   "0.44",    "Poor — market in downtrend phase"],
            ["Sortino Ratio",  "0.63",    "Acceptable — downside risk managed"],
            ["Max Drawdown",   "-17.73%", "Significant drawdown from 90-day high"],
            ["Full Kelly",     "4.47%",   "Conservative position size signal"],
            ["Half-Kelly",     "2.23%",   "Recommended size for LLM agent"],
            ["Expected Value", "+0.08%",  "Positive — strategy edge exists"],
        ],
        col_widths=[4.5*cm, 3.5*cm, 9*cm]
    ))

    # 4.4 Backtesting
    items.append(h2("4.4  Backtesting Methodology"))
    items.append(body(
        "The backtesting module performs a <b>walk-forward simulation</b> on real historical "
        "price data fetched from Yahoo Finance (GC=F). Each candle invokes the full Claude "
        "agent pipeline independently, making the backtest a true replay of the live system."
    ))
    items.append(code(
        "Candles 1–19   → Warmup (compute Bollinger Bands requires 20 rows)\n"
        "Candle  20     → First live decision\n"
        "Candles 21–N   → Replay one candle at a time, 1 Claude call per candle"
    ))
    items.append(make_table(
        ["Parameter", "Value", "Reason"],
        [
            ["Data source",  "GC=F via yfinance",   "Real historical Gold Futures prices"],
            ["Primary TF",   "1-hour candles, 60d", "Matches live agent refresh cadence"],
            ["Fallback TF",  "Daily candles, 6mo",  "Used if 1h data unavailable"],
            ["Max candles",  "50 per run",          "Controls Claude API cost (~50 calls)"],
            ["Start capital","฿1,500",              "Mirrors paper trading initial balance"],
        ],
        col_widths=[4*cm, 5*cm, 8*cm]
    ))
    items.append(h3("Backtest Performance Metrics"))
    for b in [
        "Return % = (Final Equity - Initial Capital) / Initial Capital × 100",
        "Win Rate = Closed Winning Trades / Total Closed Trades × 100",
        "Total P&L = Sum of all closed trade P&L values (THB)",
        "R:R Ratio = Average Win / Average Loss",
    ]:
        items.append(bullet(b))

    # 4.5 Paper Trading
    items.append(h2("4.5  Paper Trading Performance Tracking"))
    items.append(body(
        "The paper trading engine records equity after every trade to build a continuous "
        "P&amp;L curve. All state is persisted in <b>MongoDB Atlas</b> for cross-session "
        "continuity and cloud deployment support."
    ))
    items.append(code(
        "Equity          = Cash Balance + (Position Size × Current Price)\n"
        "Unrealized P&L  = (Position Size × Current Price) - Entry Cost\n"
        "Realized P&L    = Sum of all closed trade profits and losses"
    ))
    items.append(sp(8))
    items.append(Paragraph(
        "<i>Note: This system uses paper trading only — no real money is involved. "
        "Starting balance of ฿1,500 is simulated to mirror AOM NOW minimum trade size.</i>",
        ParagraphStyle("note", fontSize=9, leading=14, textColor=MID,
                       fontName="Helvetica-Oblique", leftIndent=12, rightIndent=12,
                       borderColor=GOLD, borderWidth=0.8, borderPad=8,
                       backColor=colors.HexColor("#FFFBF0"))
    ))

    return items


# ── Build PDF ─────────────────────────────────────────────────────────────────
def build_pdf():
    doc = SimpleDocTemplate(
        OUTPUT,
        pagesize=A4,
        leftMargin=2.2*cm, rightMargin=2.2*cm,
        topMargin=2.2*cm,  bottomMargin=2.2*cm,
        title="Thong Yip Thong Yod — Research Report",
        author="Team 3, Thammasat University",
        subject="AI-Powered Gold Trading Agent",
    )

    story = []
    story += cover_page()
    story += section_literature()
    story += section_methods()
    story += section_preprocessing()
    story += section_analysis()

    # Page number footer
    def on_page(canvas, doc):
        canvas.saveState()
        if doc.page > 1:
            canvas.setFont("Helvetica", 8)
            canvas.setFillColor(MID)
            canvas.drawCentredString(A4[0] / 2, 1.2*cm,
                                     f"Thong Yip Thong Yod  ·  Page {doc.page - 1}")
            canvas.setStrokeColor(GOLD)
            canvas.setLineWidth(0.5)
            canvas.line(2.2*cm, 1.6*cm, A4[0] - 2.2*cm, 1.6*cm)
        # Cover page — dark background
        else:
            canvas.setFillColor(DARK)
            canvas.rect(0, 0, A4[0], A4[1], fill=1, stroke=0)
        canvas.restoreState()

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    print(f"PDF saved → {OUTPUT}")


if __name__ == "__main__":
    build_pdf()

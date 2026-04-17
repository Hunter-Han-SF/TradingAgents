"""Finnhub data vendor implementation for TradingAgents.

Provides OHLCV stock data, technical indicators (via stockstats),
financial statements, company news, and insider transactions.
Free tier: 60 API calls/minute.
"""

import os
import logging
import requests
import pandas as pd
from datetime import datetime, timedelta

from .config import get_config
from .stockstats_utils import _clean_dataframe

logger = logging.getLogger(__name__)

API_BASE_URL = "https://finnhub.io/api/v1"


class FinnhubRateLimitError(Exception):
    """Raised when Finnhub API rate limit is exceeded."""
    pass


# ---------------------------------------------------------------------------
# Shared utilities
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    """Retrieve Finnhub API key from environment."""
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        raise ValueError("FINNHUB_API_KEY environment variable is not set.")
    return api_key


def _make_api_request(endpoint: str, params: dict = None) -> dict | list:
    """Make a request to the Finnhub API.

    Raises:
        FinnhubRateLimitError: When rate limit is exceeded (HTTP 429).
    """
    if params is None:
        params = {}
    params["token"] = _get_api_key()

    response = requests.get(f"{API_BASE_URL}/{endpoint}", params=params, timeout=30)

    if response.status_code == 429:
        raise FinnhubRateLimitError("Finnhub API rate limit exceeded")

    response.raise_for_status()
    return response.json()


def _date_to_timestamp(date_str: str) -> int:
    """Convert YYYY-MM-DD date string to Unix timestamp."""
    return int(datetime.strptime(date_str, "%Y-%m-%d").timestamp())


# ---------------------------------------------------------------------------
# OHLCV data
# ---------------------------------------------------------------------------

def get_stock(
    symbol: str,
    start_date: str,
    end_date: str,
) -> str:
    """Return daily OHLCV data from Finnhub as CSV string.

    Args:
        symbol: Ticker symbol, e.g. "AAPL".
        start_date: Start date in yyyy-mm-dd format.
        end_date: End date in yyyy-mm-dd format.

    Returns:
        CSV string containing OHLCV data with header.
    """
    data = _make_api_request("stock/candle", {
        "symbol": symbol.upper(),
        "resolution": "D",
        "from": _date_to_timestamp(start_date),
        "to": _date_to_timestamp(end_date),
    })

    if data.get("s") == "no_data" or not data.get("c"):
        return f"No data found for symbol '{symbol}' between {start_date} and {end_date}"

    df = pd.DataFrame({
        "Date": pd.to_datetime(data["t"], unit="s"),
        "Open": data["o"],
        "High": data["h"],
        "Low": data["l"],
        "Close": data["c"],
        "Volume": data["v"],
    })

    start_dt = pd.to_datetime(start_date)
    end_dt = pd.to_datetime(end_date)
    df = df[(df["Date"] >= start_dt) & (df["Date"] <= end_dt)]

    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")
    csv_string = df.to_csv(index=False)

    header = f"# Stock data for {symbol.upper()} from {start_date} to {end_date}\n"
    header += f"# Total records: {len(df)}\n"
    header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

    return header + csv_string


# ---------------------------------------------------------------------------
# OHLCV caching for indicator calculation
# ---------------------------------------------------------------------------

def _load_ohlcv_finnhub(symbol: str, curr_date: str) -> pd.DataFrame:
    """Fetch OHLCV data from Finnhub with file caching, filtered to curr_date.

    Caches to a Finnhub-prefixed file so it does not collide with yfinance cache.
    """
    config = get_config()
    curr_date_dt = pd.to_datetime(curr_date)

    today_date = pd.Timestamp.today()
    start_date = today_date - pd.DateOffset(years=5)
    start_str = start_date.strftime("%Y-%m-%d")
    end_str = today_date.strftime("%Y-%m-%d")

    os.makedirs(config["data_cache_dir"], exist_ok=True)
    data_file = os.path.join(
        config["data_cache_dir"],
        f"{symbol}-Finnhub-data-{start_str}-{end_str}.csv",
    )

    if os.path.exists(data_file):
        data = pd.read_csv(data_file, on_bad_lines="skip")
    else:
        result = _make_api_request("stock/candle", {
            "symbol": symbol.upper(),
            "resolution": "D",
            "from": _date_to_timestamp(start_str),
            "to": _date_to_timestamp(end_str),
        })

        if result.get("s") == "no_data" or not result.get("c"):
            raise ValueError(f"No OHLCV data from Finnhub for {symbol}")

        data = pd.DataFrame({
            "Date": pd.to_datetime(result["t"], unit="s"),
            "Open": result["o"],
            "High": result["h"],
            "Low": result["l"],
            "Close": result["c"],
            "Volume": result["v"],
        })
        data.to_csv(data_file, index=False)

    data = _clean_dataframe(data)
    data = data[data["Date"] <= curr_date_dt]
    return data


# ---------------------------------------------------------------------------
# Technical indicators (calculated locally via stockstats)
# ---------------------------------------------------------------------------

_INDICATOR_DESCRIPTIONS = {
    "close_50_sma": (
        "50 SMA: A medium-term trend indicator. "
        "Usage: Identify trend direction and serve as dynamic support/resistance. "
        "Tips: It lags price; combine with faster indicators for timely signals."
    ),
    "close_200_sma": (
        "200 SMA: A long-term trend benchmark. "
        "Usage: Confirm overall market trend and identify golden/death cross setups. "
        "Tips: It reacts slowly; best for strategic trend confirmation rather than frequent trading entries."
    ),
    "close_10_ema": (
        "10 EMA: A responsive short-term average. "
        "Usage: Capture quick shifts in momentum and potential entry points. "
        "Tips: Prone to noise in choppy markets; use alongside longer averages for filtering false signals."
    ),
    "macd": (
        "MACD: Computes momentum via differences of EMAs. "
        "Usage: Look for crossovers and divergence as signals of trend changes. "
        "Tips: Confirm with other indicators in low-volatility or sideways markets."
    ),
    "macds": (
        "MACD Signal: An EMA smoothing of the MACD line. "
        "Usage: Use crossovers with the MACD line to trigger trades. "
        "Tips: Should be part of a broader strategy to avoid false positives."
    ),
    "macdh": (
        "MACD Histogram: Shows the gap between the MACD line and its signal. "
        "Usage: Visualize momentum strength and spot divergence early. "
        "Tips: Can be volatile; complement with additional filters in fast-moving markets."
    ),
    "rsi": (
        "RSI: Measures momentum to flag overbought/oversold conditions. "
        "Usage: Apply 70/30 thresholds and watch for divergence to signal reversals. "
        "Tips: In strong trends, RSI may remain extreme; always cross-check with trend analysis."
    ),
    "boll": (
        "Bollinger Middle: A 20 SMA serving as the basis for Bollinger Bands. "
        "Usage: Acts as a dynamic benchmark for price movement. "
        "Tips: Combine with the upper and lower bands to effectively spot breakouts or reversals."
    ),
    "boll_ub": (
        "Bollinger Upper Band: Typically 2 standard deviations above the middle line. "
        "Usage: Signals potential overbought conditions and breakout zones. "
        "Tips: Confirm signals with other tools; prices may ride the band in strong trends."
    ),
    "boll_lb": (
        "Bollinger Lower Band: Typically 2 standard deviations below the middle line. "
        "Usage: Indicates potential oversold conditions. "
        "Tips: Use additional analysis to avoid false reversal signals."
    ),
    "atr": (
        "ATR: Averages true range to measure volatility. "
        "Usage: Set stop-loss levels and adjust position sizes based on current market volatility. "
        "Tips: It's a reactive measure, so use it as part of a broader risk management strategy."
    ),
    "vwma": (
        "VWMA: A moving average weighted by volume. "
        "Usage: Confirm trends by integrating price action with volume data. "
        "Tips: Watch for skewed results from volume spikes; use in combination with other volume analyses."
    ),
    "mfi": (
        "MFI: The Money Flow Index is a momentum indicator that uses both price and volume to measure buying and selling pressure. "
        "Usage: Identify overbought (>80) or oversold (<20) conditions and confirm the strength of trends or reversals. "
        "Tips: Use alongside RSI or MACD to confirm signals; divergence between price and MFI can indicate potential reversals."
    ),
}


def get_indicator(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
    interval: str = "daily",
    time_period: int = 14,
    series_type: str = "close",
) -> str:
    """Calculate technical indicators using stockstats on Finnhub OHLCV data.

    Args:
        symbol: Ticker symbol.
        indicator: Technical indicator name (e.g. "rsi", "macd").
        curr_date: Current trading date, YYYY-mm-dd.
        look_back_days: Number of days to look back.
        interval: Time interval (unused, kept for signature compatibility).
        time_period: Calculation period (unused, kept for signature compatibility).
        series_type: Price type (unused, kept for signature compatibility).

    Returns:
        Formatted string with indicator values and description.
    """
    from stockstats import wrap
    from dateutil.relativedelta import relativedelta

    if indicator not in _INDICATOR_DESCRIPTIONS:
        raise ValueError(
            f"Indicator {indicator} is not supported. "
            f"Please choose from: {list(_INDICATOR_DESCRIPTIONS.keys())}"
        )

    curr_date_dt = datetime.strptime(curr_date, "%Y-%m-%d")
    before = curr_date_dt - relativedelta(days=look_back_days)

    data = _load_ohlcv_finnhub(symbol, curr_date)
    df = wrap(data)
    df["Date"] = df["Date"].dt.strftime("%Y-%m-%d")

    # Trigger stockstats calculation
    df[indicator]

    # Build lookup dict
    result_dict = {}
    for _, row in df.iterrows():
        date_str = row["Date"]
        value = row[indicator]
        result_dict[date_str] = str(value) if not pd.isna(value) else "N/A"

    # Build output string for the lookback window
    current_dt = curr_date_dt
    ind_string = ""
    while current_dt >= before:
        date_str = current_dt.strftime("%Y-%m-%d")
        value = result_dict.get(date_str, "N/A: Not a trading day (weekend or holiday)")
        ind_string += f"{date_str}: {value}\n"
        current_dt = current_dt - relativedelta(days=1)

    return (
        f"## {indicator} values from {before.strftime('%Y-%m-%d')} to {curr_date}:\n\n"
        + ind_string
        + "\n\n"
        + _INDICATOR_DESCRIPTIONS.get(indicator, "No description available.")
    )


# ---------------------------------------------------------------------------
# Fundamentals
# ---------------------------------------------------------------------------

def get_fundamentals(ticker: str, curr_date: str = None) -> str:
    """Get company fundamentals from Finnhub.

    Args:
        ticker: Ticker symbol of the company.
        curr_date: Current date (unused, kept for signature compatibility).

    Returns:
        Formatted string with company profile and key financial metrics.
    """
    try:
        profile = _make_api_request("stock/profile2", {"symbol": ticker.upper()})
        metrics_resp = _make_api_request("stock/metric", {
            "symbol": ticker.upper(),
            "metric": "all",
        })

        metric = metrics_resp.get("metric", {})

        # Scale market cap from millions to actual value
        market_cap = metric.get("marketCapitalization")
        if market_cap is not None:
            market_cap = market_cap * 1_000_000

        fields = [
            ("Name", profile.get("name")),
            ("Sector", profile.get("finnhubIndustry")),
            ("Market Cap", market_cap),
            ("PE Ratio (TTM)", metric.get("peNormal")),
            ("PE Excl. Extra (TTM)", metric.get("peExclExtra")),
            ("EPS (TTM)", metric.get("epsInclExtraTTM")),
            ("Forward PE", metric.get("peForward")),
            ("Revenue (TTM)", metric.get("revenueGrowthQuarterlyYoy")),
            ("Profit Margin", metric.get("netProfitMarginTTM")),
            ("Return on Equity", metric.get("roeTTM")),
            ("Return on Assets", metric.get("roaTTM")),
            ("52 Week High", metric.get("52WeekHigh")),
            ("52 Week Low", metric.get("52WeekLow")),
            ("10 Day Volume", metric.get("10DayAverageTradingVolume")),
        ]

        lines = []
        for label, value in fields:
            if value is not None:
                lines.append(f"{label}: {value}")

        header = f"# Company Fundamentals for {ticker.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + "\n".join(lines)

    except Exception as e:
        return f"Error retrieving fundamentals for {ticker}: {str(e)}"


# ---------------------------------------------------------------------------
# Financial statements
# ---------------------------------------------------------------------------

def _get_financials(ticker: str, statement: str, freq: str, curr_date: str = None) -> str:
    """Shared helper for financial statement retrieval.

    Args:
        ticker: Ticker symbol.
        statement: "ic" (income), "bs" (balance), or "cf" (cashflow).
        freq: "annual" or "quarterly".
        curr_date: Cutoff date for look-ahead bias filtering.
    """
    data = _make_api_request("stock/financials", {
        "symbol": ticker.upper(),
        "statement": statement,
        "freq": freq,
    })

    financials = data.get("data", {}).get("financials", [])
    if not financials:
        return ""

    df = pd.DataFrame(financials)

    if curr_date and "period" in df.columns:
        cutoff = pd.Timestamp(curr_date)
        df["period_dt"] = pd.to_datetime(df["period"], errors="coerce")
        df = df[df["period_dt"] <= cutoff]
        df = df.drop(columns=["period_dt"])

    return df.to_csv(index=False)


def get_balance_sheet(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str = None,
):
    """Get balance sheet data from Finnhub."""
    try:
        result = _get_financials(ticker, "bs", freq, curr_date)
        if not result:
            return f"No balance sheet data found for symbol '{ticker}'"

        header = f"# Balance Sheet data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + result

    except Exception as e:
        return f"Error retrieving balance sheet for {ticker}: {str(e)}"


def get_cashflow(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str = None,
):
    """Get cash flow data from Finnhub."""
    try:
        result = _get_financials(ticker, "cf", freq, curr_date)
        if not result:
            return f"No cash flow data found for symbol '{ticker}'"

        header = f"# Cash Flow data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + result

    except Exception as e:
        return f"Error retrieving cash flow for {ticker}: {str(e)}"


def get_income_statement(
    ticker: str,
    freq: str = "quarterly",
    curr_date: str = None,
):
    """Get income statement data from Finnhub."""
    try:
        result = _get_financials(ticker, "ic", freq, curr_date)
        if not result:
            return f"No income statement data found for symbol '{ticker}'"

        header = f"# Income Statement data for {ticker.upper()} ({freq})\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + result

    except Exception as e:
        return f"Error retrieving income statement for {ticker}: {str(e)}"


# ---------------------------------------------------------------------------
# News
# ---------------------------------------------------------------------------

def get_news(ticker: str, start_date: str, end_date: str) -> str:
    """Get company-specific news from Finnhub.

    Args:
        ticker: Stock symbol for news articles.
        start_date: Start date in yyyy-mm-dd format.
        end_date: End date in yyyy-mm-dd format.

    Returns:
        Formatted string with news articles.
    """
    try:
        articles = _make_api_request("company-news", {
            "symbol": ticker.upper(),
            "from": start_date,
            "to": end_date,
        })

        if not articles:
            return f"No news found for {ticker} between {start_date} and {end_date}"

        news_str = ""
        for article in articles:
            headline = article.get("headline", "No title")
            summary = article.get("summary", "")
            source = article.get("source", "Unknown")
            url = article.get("url", "")
            ts = article.get("datetime")
            date_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d") if ts else "Unknown"

            news_str += f"### {headline} (source: {source}, date: {date_str})\n"
            if summary:
                news_str += f"{summary}\n"
            if url:
                news_str += f"Link: {url}\n"
            news_str += "\n"

        return f"## {ticker} News, from {start_date} to {end_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error retrieving news for {ticker}: {str(e)}"


def get_global_news(curr_date: str, look_back_days: int = 7, limit: int = 50) -> str:
    """Get global market news from Finnhub.

    Args:
        curr_date: Current date in yyyy-mm-dd format.
        look_back_days: Number of days to look back (default 7).
        limit: Maximum number of articles (default 50).

    Returns:
        Formatted string with global market news articles.
    """
    try:
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = curr_dt - timedelta(days=look_back_days)
        start_date = start_dt.strftime("%Y-%m-%d")

        articles = _make_api_request("market-news", {
            "category": "general",
            "from": start_date,
            "to": curr_date,
        })

        if not articles:
            return f"No global news found for {start_date} to {curr_date}"

        news_str = ""
        for article in articles[:limit]:
            headline = article.get("headline", "No title")
            summary = article.get("summary", "")
            source = article.get("source", "Unknown")
            url = article.get("url", "")

            news_str += f"### {headline} (source: {source})\n"
            if summary:
                news_str += f"{summary}\n"
            if url:
                news_str += f"Link: {url}\n"
            news_str += "\n"

        return f"## Global Market News, from {start_date} to {curr_date}:\n\n{news_str}"

    except Exception as e:
        return f"Error retrieving global news: {str(e)}"


# ---------------------------------------------------------------------------
# Insider transactions
# ---------------------------------------------------------------------------

def get_insider_transactions(symbol: str) -> str:
    """Get insider transactions from Finnhub.

    Args:
        symbol: Ticker symbol.

    Returns:
        CSV string with insider transaction data.
    """
    try:
        data = _make_api_request("stock/insider-transactions", {
            "symbol": symbol.upper(),
        })

        transactions = data.get("data", [])
        if not transactions:
            return f"No insider transactions data found for symbol '{symbol}'"

        df = pd.DataFrame(transactions)
        csv_string = df.to_csv(index=False)

        header = f"# Insider Transactions data for {symbol.upper()}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"

        return header + csv_string

    except Exception as e:
        return f"Error retrieving insider transactions for {symbol}: {str(e)}"

import hashlib
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd
import yfinance as yf

FIELDS = ["Open", "High", "Low", "Close", "Volume"]
_DEFAULT_CACHE = Path(__file__).parent / ".cache"


@dataclass
class CoverageReport:
    """Which tickers made it into the study, and why the rest did not.

    Silently dropping tickers is how a study ends up describing a universe
    nobody chose. Every exclusion is counted and attributed to a cause.
    """

    requested: list[str] = field(default_factory=list)
    included: list[str] = field(default_factory=list)
    excluded_short_history: dict[str, int] = field(default_factory=dict)
    failed_download: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"Tickers solicitados: {len(self.requested)} | "
            f"incluidos: {len(self.included)} | "
            f"excluidos por historia corta: {len(self.excluded_short_history)} | "
            f"fallos de descarga: {len(self.failed_download)}"
        )


def _download(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Raw yfinance call, isolated so tests can replace it without touching the network."""
    return yf.download(
        tickers,
        start=start,
        end=end,
        auto_adjust=True,
        progress=False,
        group_by="column",
    )


def _cache_path(cache_dir: Path, tickers: list[str], start: str, end: str) -> Path:
    """Content-addressed cache name.

    Uses md5 rather than the builtin hash(): Python randomises string hashing
    per process, so a builtin hash would miss the cache on every fresh run and
    silently re-download the whole universe.
    """
    key = f"{'-'.join(sorted(tickers))}_{start}_{end}"
    digest = hashlib.md5(key.encode()).hexdigest()[:12]
    return cache_dir / f"batch_{digest}.parquet"


def _fetch_batch(
    tickers: list[str], start: str, end: str, cache_dir: Path, max_retries: int
) -> pd.DataFrame | None:
    path = _cache_path(cache_dir, tickers, start, end)
    if path.exists():
        return pd.read_parquet(path)

    for attempt in range(max_retries):
        try:
            frame = _download(tickers, start, end)
        except Exception:
            if attempt == max_retries - 1:
                return None
            time.sleep(2.0**attempt)
            continue
        cache_dir.mkdir(parents=True, exist_ok=True)
        frame.to_parquet(path)
        return frame
    return None


def load_ohlcv(
    tickers: list[str],
    start: str,
    end: str,
    cache_dir: Path | None = None,
    min_obs: int = 252,
    batch_size: int = 50,
    max_retries: int = 3,
) -> tuple[pd.DataFrame, CoverageReport]:
    """Download an OHLCV panel, caching each batch to disk.

    Columns are a MultiIndex of (field, ticker). Repeated runs read parquet
    instead of the network, which is what makes the study reproducible without
    depending on a vendor being up.
    """
    cache_dir = cache_dir or _DEFAULT_CACHE
    coverage = CoverageReport(requested=list(tickers))

    frames: list[pd.DataFrame] = []
    for i in range(0, len(tickers), batch_size):
        batch = tickers[i : i + batch_size]
        frame = _fetch_batch(batch, start, end, cache_dir, max_retries)
        if frame is None:
            coverage.failed_download.extend(batch)
            continue
        frames.append(frame)

    if not frames:
        return pd.DataFrame(), coverage

    panel = pd.concat(frames, axis=1).sort_index()

    keep: list[str] = []
    available = set(panel.columns.get_level_values(1))
    for ticker in tickers:
        if ticker in coverage.failed_download:
            continue
        if ticker not in available:
            coverage.excluded_short_history[ticker] = 0
            continue
        n_obs = int(panel[("Close", ticker)].notna().sum())
        if n_obs < min_obs:
            coverage.excluded_short_history[ticker] = n_obs
        else:
            keep.append(ticker)

    coverage.included = keep
    if not keep:
        return pd.DataFrame(), coverage

    columns = pd.MultiIndex.from_product([FIELDS, keep])
    return panel.reindex(columns=columns), coverage

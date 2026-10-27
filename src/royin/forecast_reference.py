"""Causal descriptive horizon returns; never a calibrated forecast or trading signal."""

import hashlib
import json
from decimal import Inexact, localcontext

from royin.datasets import validate_candles
from royin.market_data import CandleSeries


def historical_return_reference(series, *, cutoff):
    """Non-overlapping close-to-close segments ending at the recorded cutoff.

    Segments can still be serially dependent. Their quantiles describe past prices,
    exclude execution costs, and must not be treated as future probabilities.
    """
    if (type(series) is not CandleSeries or type(cutoff) is not int or cutoff <= 0
            or series.interval_seconds != 300 or series.incomplete_bins):
        raise ValueError("Reference requires complete five-minute source bars")
    candles=tuple(c for c in series.candles if c.open_time+300 <= cutoff)
    if not 40 <= len(candles) <= 200 or candles[-1].open_time+300 != cutoff:
        raise ValueError("Reference requires40..200 bars through the exact cutoff")
    validate_candles(candles,300,now=cutoff)
    closes=[c.close for c in candles]
    bound=json.dumps([[c.open_time,str(c.close)] for c in candles],separators=(",",":"))
    horizons=[]
    with localcontext() as ctx:
        ctx.prec=36
        ctx.traps[Inexact]=False
        for seconds in (900,3600,10800):
            step=seconds//300
            values=sorted(closes[i]/closes[i-step]-1 for i in range(len(closes)-1,step-1,-step))
            n=len(values)
            row=dict(seconds=seconds,segments=n,status="DESCRIPTIVE" if n>=4 else "INSUFFICIENT_SEGMENTS",
                     q10=None,q50=None,q90=None)
            if n>=4:
                row.update(q10=str(values[(n+9)//10-1]),
                           q50=str((values[(n-1)//2]+values[n//2])/2),
                           q90=str(values[(9*n+9)//10-1]))
            horizons.append(row)
    return dict(policy="PAST_NONOVERLAPPING_RETURNS_V1",status="HISTORICAL_ONLY_NOT_FORECAST",
                cutoff=cutoff,interval_seconds=300,closed_bars=len(candles),
                input_sha256=hashlib.sha256(bound.encode()).hexdigest(),horizons=horizons)

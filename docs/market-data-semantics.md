# Wallex native-hour history semantics and source contract

Contract: `WALLEX_NATIVE_60_SOURCE_V1`. Source decision was frozen before new
requests or any return calculation in `config/native-hour-source-plan.json`, SHA256
`fd94f5797fb35ce3cffe75caa7a04e3314f2334d3d58f3dfc1f90692567f4570`.
No strategy, return, model, account or order evaluation was performed by this task.

Result: **DATA_READY_FOR_EVALUATION / DIAGNOSTIC_ONLY**. There are 623 real native
hourly bars in two contiguous segments. This is independent native-source quality
acceptance, not legacy T02 acceptance, statistical sufficiency, permission to change
the experiment timeframe, or authorization for validation/holdout selection.
Exchange-attested timestamp meaning and volume asset remain unknown; a consumer
must explicitly resolve or disclose the timestamp/execution assumption before
claiming causal trading results. The pointer deliberately limits use meanwhile.

## Sources and evidence labels

- **R:** No challenge rule requiring exact equality between two candle resolutions
  was established. That was an internal research gate, retained for legacy data.
- **S:** [Wallex candles documentation](https://developers.wallex.ir/docs/basic-services-candles),
  read 2026-10-21 UTC, documents GET `/v1/udf/history`, OHLCV arrays and one-hour
  grouping for `resolution=60`. Short literal: `resolution`. It does not specify
  start/end labeling, empty intervals, volume asset, revision/finality, row caps
  or inclusive/exclusive endpoint behavior.
- **S:** [Official linked Swagger](https://developers.wallex.ir/assets/files/basic-services-89626420b5f06e4d7a2dc9206cdeb192.json)
  documents integer Unix `from`/`to`. Its requiredness/resolution examples differ
  from the prose documentation; neither is proof of the observed implementation.
- **S:** [Wallex introduction](https://developers.wallex.ir/docs) describes Unix
  timestamps in seconds. The captures independently have second-scale cadence.
- **S/D:** [TradingView UDF documentation](https://www.tradingview.com/charting-library-docs/latest/connecting_data/UDF/)
  defines UTC-second bar timestamps and an exclusive right boundary;
  [bar update conventions](https://www.tradingview.com/charting-library-docs/latest/connecting_data/Datafeed-Issues/)
  expect interval-start labels. These explain the research interpretation of a UDF
  service, but do not prove Wallex implements it exactly: Wallex returned an
  inclusive `to` in the closed samples and ignored `15` in one sample.
- **U:** Backend construction/cache bugs, the internal reason for cross-resolution
  differences, and whether historical bars can be revised are not established.
  MCP history would not be an independent price reference to the same backend.

The user-reported competition deadline is 2026-10-23 23:50 Asia/Tehran. Source
timestamps, request/receive UTC times and the frozen cutoff are in the plan and
quality JSON; no future or open bar entered the historical normalized outputs.

## Offline reproduction before network

All previous raw captures were SHA256-checked before parsing. Full sanitized
field-level details and timestamp profiles are in `research/native-hour-data-quality.json`;
the raw files remain ignored. Two rejected and two accepted days are explicitly
reproduced below; these are previous multi-resolution decisions, not new labels.

| UTC day | Previous / replay | Minute raw SHA256 | Native raw SHA256 |
|---|---|---|---|
| 2026-09-14 | REJECTED / REJECTED | `58f41e380fe89847a76f7768724044195cbe8f0d8becb4e890f17380f45461a1` | `59292e259efa8e3c0836bd4bcde55d18a619a89a7c38dc3f9ed308e1665472ae` |
| 2026-09-15 | REJECTED / REJECTED | `f778add0a2cbe403286051cad15b24274c275bd8933b6e033a7c1b8df1ca6a08` | `e3c644abb2ae1d310a4e15d40ef4e6f8191720c94f01962d37b1c0dbb97e4893` |
| 2026-09-17 | ACCEPTED / ACCEPTED | `f5dfbaa6883189192648d21b472bb35f9792d9507ea848df66f3d6a469184458` | `416a463096413596db94eef560611ebee397eff01be4c2f00842555addab7204` |
| 2026-09-18 | ACCEPTED / ACCEPTED | `505b7781bb8506da28331cc600d58cfd9a8732cf4ed75cc52845beaca92c7f24` | `b7d277d3802af61d7f614063fe843fbd774359af3bf49fd6aeafa707c6eb4d24` |

Each of these daily captures contains 1441 minute or 25 hourly rows: the exact
`to` row is present, then excluded for the internal `[from,to)` contract. There
are no duplicate/unordered timestamps in these four days. Spacing is 60/3600s,
not milliseconds; no Tehran conversion or arbitrary shift was applied.

Across the seven price-mismatched September USDTTMN days: 15 hours differ in
**open**, five also differ in **high**; low, close, volume and timestamps agree.
For all these differing fields, diagnostic aggregation of nonzero-volume minutes
matches the native values. Example, 2026-09-14 01:00 UTC (`1789347600`):
minute-derived open `232814`, native open `232719`; the first minute has volume
zero and price `232814`, while the first nonzero-volume minute opens `232719`.
Zero-volume minutes can also change price, so simple last-trade carry is **not**
proven. No zero-volume row was removed from any accepted output.

This explanation is not universal. T02 first-day BTC/ETH raw replay also finds
low/close differences (BTC: low4, close2, open5, high1; ETH: low4, close1, open8,
high2 field occurrences). Those rejected datasets remain rejected. The host's
Decimal aggregation is not shown to be defective; no parser/unit fix was justified.

## New bounded experiment

Actual public API GETs: **40/80**, estimate40, concurrency1, spacing1.1s,
timeout20s, retries0. No account/model/MCP calls. Documentation browsing is
separate from this REST counter; browser search transport internals are unknown.
The collector reserves/counts an attempt before HTTP and stores each request time,
receive time, exact query, raw SHA256 and an allowlist of public cache headers.
No raw headers or credentials are logged.

Capture: `data/round-2-data/20261021T213210Z_2e0f3a63/manifest.json`.
Immutable offline replay/output:
`data/round-2-data/20261021T213718Z_f8e726a7/manifest.json`.
Actual source hashes of each code version are in those manifests. These runs used
a dirty tree based on `a8a5294488f1b330ca0f8df5f9800c2b2d6962fb`; they must not be
attributed to an unmodified commit. Raw evidence and normalized files are ignored.

Observed:

1. A fixed closed hour requested with `1` returned61 rows, cadence60; `60`
   returned2, cadence3600. `15` returned the same61 rows and raw hash as `1`.
   No assumption based solely on the query resolution is accepted.
2. With `to=1789351200`, native includes that timestamp; `to=1789351199`
   excludes it. Enlarging the window preserves overlapping values.
3. Immediate duplicate minute/native queries have identical raw hashes. All12
   older same-query hourly captures available for comparison also have identical
   hashes to the new observations. This shows no observed revision in those
   samples, not a general immutability guarantee.
4. Responses advertise `cache-control: max-age=15`; repeated current queries have
   equal response Date and hash. This is consistent with caching, not proof that
   cache caused the OHLC differences.
5. Native September22 lacks exactly `1790082000` (13:00 UTC). The day query and
   overlapping query both omit it. No-trade vs missing-feed cause is unknown.
   The old minute source also had missing rows. There is no synthetic replacement.
6. Each complete day has25 native rows including its right boundary; no daily
   truncation is observed. This does not establish a maximum response length or
   pagination contract. Historical/current fetch times are distinct from bar times.

## Native-hour source contract and coverage

Acceptance uses only native `60`; exact UTC-hour alignment, sorted/unique times,
positive finite consistent OHLC, nonnegative exact Decimal volume, closed cutoff,
hash-bound source/asset/interval/window metadata. The whole response is rejected
for a malformed row. A genuine missing hour splits coverage into separate runs;
it is never hidden by joining across it. Adjacent days join only with contiguous
timestamps; returned endpoint overlaps must be identical, including volume.
Partial-day source status remains REJECTED for full-day coverage, while its valid
contiguous pieces are identified separately. All623 observed rows are retained.

| Contiguous UTC interval `[start,end)` | Bars / hours | Complete 72h windows after initial31h warmup, geometric upper bound |
|---|---:|---:|
| Sep01 00:00 — Sep22 13:00 | 517 | 6 |
| Sep22 14:00 — Sep27 00:00 | 106 | 1 |

These seven possible windows are not assigned experiment roles and are not
independent statistical samples. Warmup is now hourly:31 bars require31 hours,
not the old7h45m. The old September development windows have coverage; old
September21–24 validation crosses the gap and is unavailable as one72h window.
September24–27 has72h plus the preceding31h within the second segment. This is
coverage only; timeframe/split changes require an explicit frozen consumer plan.
October1–8 remains development-only. Account-specific market access, volume
asset, execution fill assumptions, fee and liquidity sufficiency are not verified
by this public price-source acceptance.

## Current feed feasibility, not a running worker

Two tiny current `60` queries returned three UTC-hour timestamps, including the
current hour. The two preceding rows pass the closed-bar filter; the current row
is excluded. The repeat was within the observed cache lifetime, so it does not
prove live updates, finality, restart recovery or stability across an hour boundary.

Same-source hourly polling is feasible in shape: one history GET per cycle,
requesting a small overlapping closed tail, then dedup and compare previously seen
bars. A cautious confirmation cycle needs two GETs separated by more than15s;
timing/finality across a boundary still needs measurement. Do not claim this
observation is Shadow or T09 verification. Do not silently use native `15`.

## Commands actually run

```powershell
.\.venv\Scripts\python.exe -X utf8 -m scripts.collect_validation_data --source-plan config/native-hour-source-plan.json
.\.venv\Scripts\python.exe -X utf8 -m scripts.collect_validation_data --source-plan config/native-hour-source-plan.json --replay-source-run data/round-2-data/20261021T213210Z_2e0f3a63/manifest.json
.\.venv\Scripts\python.exe -m unittest discover -s tests -p test_native_hour_data.py -v
```

The first command consumed the40-GET frozen plan; do not repeat it as an offline
check. The second performed40 hash-checked replays and **zero HTTP GETs** into a
fresh run path. It reproduced every full-day acceptance/rejection and both
contiguous normalized outputs. Unit checks independently cover bad hash/tamper,
wrong interval/metadata, duplicate/gap/open/future, invalid volume/OHLC, cutoff,
inclusive tail and conflicting overlap. Detailed test/integration command results
are recorded in the Agent1 ignored handoff; concurrent Agent2 files are not owned
or modified here.

## Prepared support questions — not sent

1. For `/v1/udf/history`, does `t` identify the start or end of the traded interval?
   What exact event window and inclusive/exclusive `from`/`to` apply? Is a bar
   final at `t+resolution`, and what revision/availability delay can occur?
2. USDTTMN, `resolution=1/60`, UTC2026-09-14 01:00–02:00:
   minute-derived open232814 versus native232719. Minute first row has v0;
   native raw hour SHA256 `c51be4f095cf` (full hash in the quality JSON).
   How are zero-volume minute OHLC constructed? Is volume base or quote asset?
3. Why does the same fixed window with `resolution=15` return61 rows at60s
   spacing and the same bytes as `1`, while `60` returns2 rows at3600s spacing?
4. USDTTMN `resolution=60`, UTC2026-09-22 00:00–23 00:00, raw hash prefix
   `56e133b2b0c5`: 13:00 UTC is absent, including an overlapping day query.
   Does absence mean no trades, unavailable data, or a service issue? Is there
   a documented complete official source for that interval and a row/page cap?

No support message was sent. Next single step: integrator/consumer independently
verify pointer hashes, then explicitly settle the hourly timestamp/source contract
and register a compatible experiment plan; do not reuse the gapped old validation.

## Integration review, 2026-10-22 Asia/Tehran

The delivered pointer hashes and 623 normalized rows were independently verified.
The exact delivered contract bytes (original hash d3a06da0dd7e1435f4be2217bba3ee3c80a684ad6447c3eead962d684502f8da)
are archived locally at artifacts/integration-review/delivered-source-contract.md.
Current documentation paths and test names were normalized; frozen data-plan bytes
remain unchanged. Capture hashes refer to the original source, not later edits.
The current snapshot observer may accept a shorter leading history prefix only
with explicit requested/actual coverage and enough contiguous closed warmup bars;
internal gaps, invalid cadence and missing recent closed bars remain rejected.
This does not relax the historical manifest contract or establish finality.
See candidate-evaluation.md for the diagnostic outcomes and closed execution gates.

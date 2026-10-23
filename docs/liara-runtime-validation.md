# Liara runtime validation — 2026-10-23

Trading source: **026a1bea29820fc4b43e67f6cc1cea13e99b54ea**.
Application: `royin-trading-agent`; mission: `fresh_live_20261023_9`;
service: `svc_live_20261023_9`. The explicit fresh financial lane is active,
separate from the historical UNKNOWN canary, with no paper fills.

At17:55UTC /21:25Tehran, actual health/readiness both returned HTTP200,
LIVE_BOUNDED/RUNNING/ready=true, heartbeat below30seconds. The financial ledger
contained zero orders/fills and4,000,000TMN allocated cash. An allocated balance
is not a new exchange balance observation or proof of trading profit.

- [Process health](https://royin-trading-agent.liara.run/healthz)
- [Entry readiness](https://royin-trading-agent.liara.run/readyz)

Ready means no recorded runtime entry blocker. Market data, model output and
execution gates still govern entry. The root URL is not the dashboard. No public
endpoint exposes keys, raw model traffic or an order interface.

## Actual release method

One1GB workload and2GB persistent `royin-state` disk mounted at `/state` use the
team's dedicated network. Scale is one; zero-downtime overlap is disabled. Actual
PID1 UID/GID is10001. Local financial owners exited before activation.

External image builds failed/timed out on base/PyPI availability, private-base
registry authorization and a bounded large-upload WriteTimeout. Failures remain
recorded; the uncertain upload did not establish image publication or trigger a
release request. The working route reuses the existing tested dependency image
and transfers immutable committed source to:

`/state/releases/026a1bea29820fc4b43e67f6cc1cea13e99b54ea`

This is **not a newly published026a1be Docker image**. All68 allowlisted runtime-file
SHA256 hashes and actual module roots passed on Liara. Files are0400/directories
0500, owner10001. `PYTHONSAFEPATH=1` removes the old working-directory precedence;
explicit `PYTHONPATH` selects the release's `src` and root. Environment revision,
source/config bindings and actual imports agree. Data/artifact/local symlinks
retain the original persistent directories.

Source artifact SHA256:
`085ade7a49b80ad9800078227997e86301ca958810d1aa86a92ffe8bcfb36409`.
The full27-key approved environment was read back; maintenance=false,
provider=boxapi, model=gpt-6-luna. No key/state is in committed source.

## Durable state and funding

All303 original BoxAPI reservations remain unchanged. A one-time credential-bound
grant in the SAME original ledger permits **USD2.822355**,95% of operator-reported
USD2.9709. No usage/scope/counter was reset/refunded. First active inspection found
four funded HTTP reservations, USD0.01742848: three compatibility requests plus
one production attempt. A reserved attempt without a completed recorded decision
is not a valid model WAIT.

Historical canary remains UNKNOWN with original intent/reserve/counter8 and SHA256
`8bcb1259e6a633693fcf7cb6a598edc230c3eed1f44e6f62cf6bca089ad8c524`.
Fresh-lane authorization is not historical exchange finality. Linux preparation
read the dedicated account and bound a new mission to actual source/config.
Earlier missions, their raw state and historical statuses remain preserved.
Cross-platform raw config serialization differs; old hashes were not rewritten.

Mission8's actual flat restart preserved12 compared identities: balances, config,
fills, journal, model scope/usage, next analysis, orders, permit, source, transport,
bootstrap coverage. Before source026 changes, maintenance and a free exclusive
owner lock confirmed quiescence. Mission9 subsequently passed the same12-identity restart validation after its
first complete WAIT while flat; see the later acceptance checkpoint. Do not
interrupt an in-flight analysis/order merely to repeat a diagnostic.

## Financial policy and recovery

See [capital policy](dynamic-capital-policy.md) and
[funded cadence](funded-boxapi-runtime.md). Entry analysis is at most once per
900seconds, risk polling every30seconds. Bounds:323roles/647modelHTTP/22M reserved
tokens, USD1.10 per Tehran day within the grant ceiling. Do not spend merely to
consume95% credit. The first actual completed round-trip debit remains<=150000TMN.
Later sizes use stops/ATR/fees/liquidity,50%asset and80%aggregate ceilings, one
position at a time. Model confidence is not a calibrated success probability.
Drawdown/daily-loss gates and stops/forecast/deadline exits are host-controlled.

Monday finalization21:50 and end22:50Tehran are conservative team choices. The
organizer's exact Monday hour remains unconfirmed; the operator confirmed credit
extension. Friday source/demo deadline is distinct from the financial end.

For recovery retain this disk/source folder/full environment/contracts/permit and
original budget/financial databases. Restart the existing app; never rerun grant
initialization or preparation. UNKNOWN closes entries and reconciles the same
client ID; never blindly repeat a POST. Missing model state blocks new analysis
while host protection continues. No hot edits to the active source folder.

## Validation and limitations

Source026 passed493 core tests in72.733s,13 dashboard tests in2.316s, Ruff,
compileall and diff checks. A mounted Linux fixture passed47 tests in168.429s on
the preceding core; initial missing-mount fixture errors remain recorded. The new
publication guard has core regressions and actual server source-hash verification.

Entry defers the first60seconds after a five-minute close and the final60seconds
before the next, before claiming analysis. Previous histories contained199/200
required minute bars six seconds after close; an identical later ENA window
contained the missing bar and passed the unchanged parser. Longer delays still
reject. No forward filling/backdating/weaker freshness was added. Bootstrap now
preserves quant rank within durable per-symbol attempt counts, still bounded to
three attempts with unchanged spread/data/risk gates.

Earlier spread/data rejection is a host result, not AI WAIT. The real server's
synthetic BoxAPI tool/schema check passed4.375s/2HTTP; recorded production-input
compatibility passed2.153s/1HTTP. Neither is a new forecast or alpha. Alternative
provider experiments have stopped; adverse timeout results remain recorded.

The interrupted prospective paper run remains PARTIAL: hold -1389.50331768TMN,
rule -3321.877789326TMN, model arms zero fills. All24 issued forecasts were scored:
MAE0.552075percentage points versus zero-return0.255658;5 better/19worse. These do
not demonstrate profitable strategy behavior.

The localhost dashboard has local Vazirmatn/Inter fonts and distinct real/paper
balances. A read-only copy of mission9's actual cloud snapshot replaced the old
local fixture; the overview returned200 and LIVE_BOUNDED/fresh_live_20261023_9.
This is a timestamped copy, not continuous synchronization or a published cloud
dashboard. Full public-market execution replay is not established by
accounting replay or saved response hashes alone.

An exact Git archive of trading revision026a1be contains212 files, dependency
lock and tests, excluding local secrets, raw artifacts and all financial SQLite
state. SHA256: `1c7fdc888d1eb961ee32ea02482559a9f7c9a8cceaa25e0392c4eb5d94c6762d`.
Preparing this archive is not uploading or submitting it.

Private receipts stay ignored. Source/video submission, exchange fills, positive
realized return, final zero residual and uninterrupted three-day operation each
need separate evidence; none follows from health checks.

## Completed production decision — 2026-10-23, after21:36 Tehran

Mission9 recorded its first complete REAL_MODEL_ATTEMPT with host_outcome=MODEL_DECISION, research_status=CANDIDATES, no research errors and latency30.166s. BoxAPI gpt-6-luna selected research over10 markets; seven failed unchanged0.5%spread gate, leaving PEPETMN/ETHTMN/USOONTMN. Its schema/evidence-bound decision was WAIT: bearish/mixed trends, negative or unconfirmed volume pressure and no supported gross target above2% after considering reversal/cost concerns. This is a valid model decision, not timeout/fallback, and not proof that waiting was financially optimal. Zero actual orders/fills,4M allocated TMN, historical state untouched. Funded usage6HTTP/USD0.02614272 reserved, all303 legacy reservations preserved;2role attempts/3productionHTTP include the earlier incomplete attempt, not two completed forecasts. Durable next-analysis time1792779668 remains unchanged by restart; no cadence reset.


## Mission9 restart acceptance — 2026-10-23, 21:40 Tehran

After the first complete valid BoxAPI WAIT and while financially flat, one actual Liara restart returned200. An intermediate PAUSED_RESTART receipt was retained; subsequent health returned200/RUNNING with4second heartbeat. Post-restart validation on the resumed worker confirmed all12 identities unchanged: balances, bootstrap counts, config, fills, journal, model scope, model usage, next analysis, orders, permit, source and transport. No extra model request/order was granted. Cloud source remains026a1be; this phase changes documentation only. Exact212-file source archive is .local/review/royin-source-026a1be.zip, SHA2561c7fdc888d1eb961ee32ea02482559a9f7c9a8cceaa25e0392c4eb5d94c6762d; excluded secrets/raw state verified. Local dashboard now reads a timestamped copy of actual mission9 snapshot, not continuous cloud synchronization. Source/video upload and future profit/zero residual remain UNCONFIRMED. No Git push.

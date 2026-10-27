# PUMP WAIT investigation, named market facts and Wallex credential rotation

## Observed decision, not a submission error

The operator's quoted explanation is original zero-based trace197, issued2026-10-25T16:52:25.639455UTC /20:22:25Tehran, cutoff1792947000. A fixed copy of the original manifest has SHA `d781c28d93841ff5c823e825bb5c8bc45d7dfa6c722b95e4f7190bafd986cf3b`,200 traces. The copy and raw diagnostics are private under `/state/diagnostics/pump-wait-20261025`; the original manifest and issuance timestamps were not rewritten.

| Recorded PUMPTMN fact | Value |
|---|---:|
| Last closed price / prior20-bar high | 1158 /1157TMN |
| Break above that high | 0.08636% |
| Trigger volume / prior20-bar mean | 0.51289× |
| RSI14 | 54.71698, normal |
| Close-location volume-pressure proxy | +0.36267, not executed buyer flow |
|20-bar path efficiency | 0.24324 |
| Fresh bid / ask | 1152 /1157TMN |
| Ask relative to last close | −0.08636% |
| Recorded spread fraction | 0.43403% |
| Assumed fee per side / slippage per side | 0.30% /0.05% |
| Per-unit break-even return from last close | 1.05219% |
| Cash-debit break-even, including fee-asset/lot/residual cases | **1.45243%** |
| Model terminal median / horizon | −0.20% /4hours |

The breakout, RSI and pressure observations were real inputs. Trigger volume was below its prior average; positive pressure did not make it elevated traded volume. The entry hurdle was dynamic, not a fixed1.45% profit requirement. Exact fee observation through the credit-account API confirmed PUMPTMN's0.003 taker rate at the later credential check. The scanner's symmetric0.006 round-trip assumption was not reduced on speculation. Quote movement, spread, fee/slippage assumptions, stepped lots and residual economics all affect this hurdle.

The recorded research capacity was SELLABLE_WITH_BOUNDED_RESIDUAL at150000TMN, with four conditional fee-asset cases and residual marks within the existing500TMN ceiling. Thus this quoted case was not rejected for insufficient capacity, unknown order state, an API submission failure or an exhausted model budget. It was MODEL_DECISION/WAIT: the model did not authorize ENTER. A forecast of future growth sufficient to cover costs is different from a price level already being reached before entry. Around this snapshot's terms,1.45243% from1158 is about1174.82TMN, but that is a conditional break-even reference, not a standalone limit-order recommendation or a forecast that the level will be reached.

## Reproduced interpretation failures and their limits

Six real BoxAPI/gpt-6-luna calls compared three fixed recorded contexts197,189,199 with the existing instructions and an explicit forecast-independence addendum. All were HTTP200 and all proposals were WAIT. These were retrospective context experiments, not new pre-outcome production forecasts, and are not included in forecast scoring or exchange results. Maximum conservative reservation USD0.02614272 was charged on the original funded pool; no refunds, retries, reset or orders.

One baseline free-analysis response called0.24324 path efficiency a **24.3% ask gap**, although the actual ask gap was−0.08636%. Another described a negative “24h historical q50”, although the provided history horizons were15minutes,1hour and3hours. An earlier production explanation also called negative1h/3h medians positive. These establish actual interpretation errors; they do not establish that every WAIT was wrong or that correcting a sentence creates positive expectancy.

The addendum separated conditional PRICE forecasting from cost admission, clarified that mixed-regime historical medians are not hard vetoes, and distinguished trigger volume, pressure and RSI labels. On the same recorded inputs it produced0.2% and0.6% positive1h medians for two PUMP cases, still below their1.45% and1.11% hurdles. Horizon/selection also changed in some responses. This is a small stochastic, retrospective experiment, not a clean proof of better out-of-sample forecasts or profit. Raising or forcing forecasts to clear the hurdle was not implemented.

The strategy still requires both central terminal forecast and target to clear cash costs. That is its current admission choice; q50 is not expected value, and this policy can exclude asymmetric opportunities whose median is below cost. Three quantiles without a validated payoff model are insufficient grounds to replace it with a fabricated positive-EV estimate. A general claim that green indicators imply a good entry would be unsupported.

## Implemented correction

Only `src/royin/agent.py` changed in the financial runtime relative to4beb. The new `ENTRY_DOSSIER_COMPACT_V6` keeps `closed_bar_structure` and `execution_cost_context` as named objects, removing two levels of positional decoding that allowed price-gap/path-efficiency confusion. The outer indicative metric table remains; all accepted candidates, evidence union, exact prices/identities and the original full-dossier hash remain. Host fee/lot arithmetic, validators and financial gates are unchanged.

Named objects increase request size. The installed Pydantic-AI2.59.0 `ProcessHistory` capability now replaces ONLY the obsolete host-generated catalog-preview user message after its research tool has completed. The first HTTP request retains the full catalog preview; the second retains its SHA, all assistant tool-call IDs/arguments, the exact fresh tool result and final output bindings. The complete host trace/context remains unchanged. Before research, non-research roles and untrusted tool text are not compacted by this rule. No candidate or cost constraint is dropped to fit the request. The original31744-byte request bound, two HTTP/role, one research tool and zero paid repairs remain.

Entry instructions now explicitly separate price forecasting from cost admission and distinguish unconditional history, normal RSI and trigger volume from pressure. No model change, new provider, increased financial sizing, forecast clamping, forced entry, historical finality or budget reset was introduced.

Two new meaningful regressions initially failed on the old code: named gap/efficiency/volume attribution through reordered candidates, and completed-research history compaction preserving exact first-preview/tool-call evidence within the original SDK bound. After implementation,22 focused tests PASS. Full core **612 PASS in74.989s**; dashboard **31 PASS in10.119s**; Ruff,compileall,diff check,example config and all four paper self-checks PASS. An initial new-test semicolon lint error was fixed; source behavior did not change afterward. Graph service was unavailable, so exact source/call sites and tests were used.

A separate four-call real-provider factual comparison, two contexts per variant, asked for six quantities: ask gap, cash hurdle, path efficiency, trigger relative volume, RSI and1h historical median. Both variants answered all12 quantities correctly when explicitly asked. This confirms bounded factual readability in that task, not exclusive candidate superiority or general semantic accuracy. The candidate's named structure also removes the ambiguous nested arrays by construction. An earlier diagnostic startup hit a SQLite lock during preflight and issued **zero model HTTP**; its log is preserved. A later separate run completed the four calls, maximum reservation USD0.01742848. The oracle uses the already declared10-significant-digit metric/5-digit historical display, not nonexistent raw precision.

## Matured forecast evidence

The fixed original manifest was scored for original trace indexes172..199 with the existing hash/snapshot/provider-output validator and exact terminal-minute diagnostic. At the fixed scoring clock:28 issued forecasts, **16 scored,12 pending,0 missing**,16 public GETs. The4h forecast quoted by the operator was still pending and was not declared correct or incorrect from intermediate prices.

On the16 matured1h forecasts, model mean absolute error was **0.555135%**, versus **0.530135%** for zero terminal return; descriptive skill was−4.7158%. Five model forecasts were closer, seven worse, four tied. There were12 positive and4 negative price outcomes, versus8 positive/4 zero/4 negative model medians. Mean model median0.025% versus mean price outcome0.269537% suggests underprediction in this particular correlated window, not a causal estimate or a direction correction to apply in production. Interval coverage87.5% and mean width1.97919% do not prove calibration. None of these point-price scores establishes executable profit, a win rate or a successful real order.

## Wallex key rotation and dashboard incident

During the controlled source handover the operator supplied a new Wallex API key. It was stored only in ignored local private files, the ignored local `.env`, and the existing financial app's environment. It was excluded from the source archive, Git and dashboard configuration. The only credential setting changed was WALLEX_API_KEY. BoxAPI funding and SUB_ACCOUNT_CLIENT_ID remained unchanged.

Five bounded read-only requests checked old/sub-accounts and new/sub-accounts,balances-detail,openOrders,fee. **Both old and new keys returned200** for the same active credit account, account fingerprint `f5fe97d66e3c9235d2311024f467b9ca65451c420615b1ec39d757e458befa85`. The new key's account reads all succeeded:5millionTMN available,0locked, no nonzero coin balances,0open orders. An initial local diagnostic used nonexistent `Balance.free`; the captured raw response was re-parsed with `Balance.available`, preserving the failed receipt and requiring zero extra GETs. That was a diagnostic reader bug, not a Wallex account error.

FreshMissionTransport binds the existing permit to the account fingerprint, not the replaceable secret. RuntimeConfig excludes secrets from its public config hash. Thus rotation required neither a new financial mission nor rewriting the original permit/config binding. Liara environment readback verified only the key setting changed at that step; the completed subsequent restart activated the new source and current platform environment. A server-side read using the new key also returned balances HTTP200. Direct `/proc/1/environ` inspection was denied even before privilege drop; no bypass was attempted, and direct PID1-secret readback is explicitly UNAVAILABLE_PERMISSION. The activation evidence is platform config readback, completed restart, new-source normal execution and server-side authenticated GET, not a fabricated direct memory attestation.

The dashboard browser's “signal is aborted” message does not establish a revoked Wallex key: the old key still worked. A financial-app restart stops its publisher; the original single publisher was restored from sourceac046 with the current ALL_LEDGER_RESERVATIONS setting. Public authenticated overview then returned200/AVAILABLE with a fresh heartbeat; health/readiness200, unauthenticated root401, normal cross-site navigation200, cross-site API403. HTML/JS/CSS hashes are unchanged. Exact browser-side cause of the prior abort remains unconfirmed; source handover/publisher interruption and the browser request abort are recorded separately.

## Actual deployment acceptance

ACTIVE immutable CONTENT_HASH_NOT_GIT_COMMIT artifact **`0d066ae7a8ccc0b476ce32079147195ce22443bf`**, source SHA `0c276be63dccd728211aff2c455736e28f7b15610d44363778970f7f7142a53a`, ZIP SHA `734e49a2959fac5f1979bd63eda211cb9ab0e6d7cca2770820a5436c7aec21c4`. All72 actual runtime files/import roots verified, same original mission9/image/disk. Backup `/state/upgrades/named-entry-20261025`; source transition SHA `2d21743dd06fec7b9fb192470ac5bdc6512b97af8df76bbbf45d942932bbcf9c`.

Backup and source-transfer exec acknowledgments timed out. Authoritative readback established complete backups and all72 immutable source files plus the exact ZIP receipt before proceeding; neither mutation was blindly repeated. Every original table in financial/signals/budget/historical DBs and original manifest matched the consistent backups before activation, apart from the authorized source-history append. All651 reservations,30 scopes including the existing pool scope,205 decisions, pending cadence, original grants/pool/health, financial intent/reserve/counter8 and historical UNKNOWN/raw SHA remained. The history now has16 receipts under its current max16; preserve all receipts. A future upgrade requires a deliberate bounded extension with tests, not deletion/reset of history.

Original mission resumed with300-second entry analysis,30-second host protection, same pooled funding authority/daily_limitnull, config/permit/deadline/capital gates. Process inventory identified one financial launcher, PID1 `python -m deploy.entrypoint`, and one publisher PID22; no second financial worker was started. An acceptance helper initially searched for the wrong launch command and failed; it was corrected to the observed entrypoint. PID1 startticks1354470026.

First completed normal V6 cycle issued **21:11:58.321Tehran**:2 BoxAPI200, request10396/25896bytes, SDK10443input/558output, actual role/source binding matched and accepted comparison VERIFIED for7symbols/3feasible. MODEL_DECISION/WAIT on ARB, q50+0.4% below its1.58% cash hurdle. Full explanation quality is not blanket-certified. At21:12:19 continuity check:653 reservations/206 traces, all651/205 old prefixes exact, scope identities/limits unchanged and usage monotonic, no new scope, original grants/config/permit/historical SHA intact, last_error empty and no entry block. **Actual exchange orders/fills/transport attempts remain0.** Successful key rotation, context repair and model calls do not establish a completed real BUY→SELL or profitability.

No Git commit/push or dashboard visual change. Next evidence needed is a prospective economically valid model entry followed by actual exchange finality, and forecast/strategy comparison on fresh data. More explanations, tests or API credit cannot substitute for that evidence.

Final continuation21:21:48Tehran: same PID1/source,651 original reservations and205 original decisions remain exact prefixes; current656/207 with another model request potentially in flight. All scope identities/limits/pool/grants/account/config/permit/historical SHA and monotonic cadence checks PASS, last_error empty, no entry block; actual orders/fills/attempts0. The last completed cycle21:17:02Tehran was another2HTTP200/MODEL_DECISION-WAIT. Authenticated public dashboard overview returned200 in3.688seconds at21:21:22Tehran,AVAILABLE with heartbeat age16seconds; reservation and recorded SDK usage AVAILABLE, assets unchanged. The source archive contains no new Wallex credential, private files are ignored, original HEAD/index unchanged, Ruff/compileall/diff checks PASS. These are time-bound observations, not a guarantee against future network/provider errors.

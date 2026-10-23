# Dashboard refresh evidence — 2026-10-23

The user requested better UI/UX and Persian/English fonts while the three-hour
paired test was active. Only the independent dashboard and documentation changed;
the frozen engine source, policy and running model worker were left untouched.

- Self-hosted variable Vazirmatn and Inter, with OFL licenses, upstream immutable
  URLs and SHA256 inventory. Two exact font routes; no directory browsing or CDN.
- Mobile-first spacing/type and restrained dark surfaces. Test progress precedes
  account/research detail. Native selects preserve the existing keyboard contract.
- Read-only projections now include the paired test and each real child run.
  Valid model decisions and host fallbacks are counted separately; raw provider
  messages and arbitrary private fields are not exported. Independent manifest
  reads are explicitly not an atomic checkpoint or synchronized chart series.
- New row selection clears old rows during loading and disables pagination.

Validation: 12 dashboard unittest cases passed, including initially failing
font-route and paired-projection regressions; Ruff and JavaScript syntax checks
passed. Before/after screenshots are ignored under
`.local/dashboard/ui-refresh-20261023/`.

Browser observations: 280/320/414px document scroll width equals client width
after fixing a long event identifier overflow. 1280px desktop was inspected.
Pause toggled aria-pressed; APMix/ENTER selection showed the recorded PEPE entry;
details opened, Escape closed them and focus returned to the detail trigger;
an unmatched symbol showed EMPTY; timezone switching changed the clock to UTC.
No console error/warning was observed in that inspection. These observations do
not establish every future state or universal accessibility compliance.

Thirteen distinct visible text/background pairs measured in the inspected state
had a minimum ratio 5.68; disabled controls, pseudo-elements and every possible
hover state were not measured. The generic kit accuracy command returned 0/52
because it looked for the kit's own examples/scripts relative to this repository.
That run measured no product score and is not counted as dashboard acceptance.
The applicable project/browser checks above remain the evidence.

The dashboard is still a localhost read-only viewer; this change does not expose
it publicly on Liara, enable live orders or prove trading profit.

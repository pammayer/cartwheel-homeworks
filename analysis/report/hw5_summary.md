# HW5 summary: judge for `internal_policy_id_shown`

## Failure definition
Question: does any assistant reply show the customer an internal policy
identifier (a token starting `cw-` such as `cw-returns`)? Fail if any reply does,
however it is formatted. Pass if none does: naming a policy in plain words,
paraphrasing it, or citing nothing is Pass. Text in tool calls and results is out
of scope because the customer never sees it. This follows the revised RESP-1
(SPEC.md).

## Labels
70 records, one per underlying case: 36 Pass (1) and 34 Fail (0), in
`analysis/state/hw5_labels/internal_policy_id_shown.jsonl`. The 100 HW4 traces
cover 70 underlying cases (the same order or product appears in several scenario
variants), so one record per case was kept by a seeded random draw
(`analysis/state/hw5_dedupe.json`).

**These labels came from a rule, not from reading each trace.** They are the HW4
judgments for this mode, which the reviewer accepted after the rule agreed with 17
of 17 earlier hand judgments and 24 of 24 spot-checks. The regex check also
produced every label that the judge was scored against.

## Split and prompt
20/40/40 stratified, seed 7 (`analysis/state/splits.json`, unchanged since):

| Set | Traces | Pass | Fail |
|---|---|---|---|
| Training | 14 | 7 | 7 |
| Development | 28 | 14 | 14 |
| Test | 28 | 15 | 13 |

Judge: `anthropic/claude-haiku-4-5-20251001` through DocETL. The prompt
(`analysis/prompts/internal_policy_id_shown-v0.txt`) has the Pass and Fail rules, the
boundaries, a note to ignore instructions quoted inside a trace, a clear Fail, a
clear Pass and a borderline case (the identifier appears only in a later reply).
All three examples come from the training set. Inputs contain only the customer's
and assistant's messages.

## Results (Pass is the positive class)

| | TP | FN | TN | FP | TPR (95% Wilson) | TNR (95% Wilson) |
|---|---|---|---|---|---|---|
| Development (v0) | 14 | 0 | 14 | 0 | 1.00 (0.78 to 1.00) | 1.00 (0.78 to 1.00) |
| Test (v0, frozen) | 15 | 0 | 13 | 0 | 1.00 (0.80 to 1.00) | 1.00 (0.77 to 1.00) |
| Regex check on test | 15 | 0 | 13 | 0 | 1.00 | 1.00 |

Files: `analysis/report/dev-internal_policy_id_shown-v0.json`,
`analysis/report/test-internal_policy_id_shown-v0.json`,
`analysis/report/test-code-baseline.json`; predictions and critiques in
`analysis/state/judges/internal_policy_id_shown-v0.json`.

There were no development disagreements, so no revision was made (the handout
allows two). v0 was frozen as written.

## Would I use the judge? No.
A perfect score on 28 traces per set is real, but the intervals still allow a true
rate near 0.77 to 0.80. More important, the task is checkable by code: the regex
matched the judge exactly, is free, deterministic and instant, and has no model
to drift. The `write-judge-prompt` skill itself lists "code-based evaluation ruled
out as infeasible" as a prerequisite, and it is not met here. The mode was chosen
because it was the only one with 30 Pass and 30 Fail labels, not because a judge
suits it. An LLM judge belongs on the fuzzier modes, such as `reply_misses_the_ask`
and `verbose_reply`, which still need more human labels.

## Caveats
- Labels for the judged mode came from a rule, so agreement with them mostly shows
  that the judge behaves like the regex.
- The judge is Claude Haiku 4.5 and the agent under review is Claude Opus, the
  same model family. That risks self-preference; it is unlikely to matter for a
  check this concrete, but it was not tested. The handout specifies gpt-4o-mini;
  the reviewer chose Claude instead, which needed one line added to
  `analysis/helpers/scale.py` (accept `ANTHROPIC_API_KEY`).
- The two skills were not installed. Their instructions were read from GitHub and
  followed.
- Total judge cost was about $0.12 (two runs of 28 traces).
- The review interface now shows the judge verdict and critique beside the
  reviewer's label, with a filter for disagreements. Test predictions are
  withheld until the judge is frozen.

# HW4 review summary

## The reviewed sample

100 distinct traces from the 250 Module 1 traces (`traces/support_traces.json`,
HW3 final run, model `claude-opus-4-6`). Each trace is a whole conversation,
merged by `cartwheel.scenario_id`. No trace counts toward two batches
(`analysis/state/sample_manifest.json`).

| Batch | Traces | How chosen |
|---|---|---|
| 1 | 30 | 15 cluster representatives + 15 uniform random (the provided `select_traces` splits 2:1, so I recombined its clustering helper to get exactly 15/15) |
| 2 | 30 | 10 each of shopper, merchant and support: one dimension (role), chosen before looking at outcomes |
| 3 | 25 | Depth searches for candidate modes and close negatives (a deterministic filter and a similarity search, both used only as leads) |
| 4 | 15 | Uniform random, seed 2026, drawn after the taxonomy was drafted |

Composition: 53 shopper, 27 merchant, 20 support sessions; 57 coverage and 43
challenge scenarios; 26 traces built around a damaged-record case.
The sample is deliberately not representative (stratified, clustered and
searched), so every fraction below is a sample fraction, not a prevalence estimate.

I wrote 131 free-text open-code notes on 87 traces (5 marked "no failure
observed"). The other 13 traces, all from batch 3, were reviewed through the
accept/reject decisions on depth-search suggestions instead.

## New modes in the final 15 traces

**0 of 15 produced a previously unseen consequential mode.**
- 9 traces fit modes that already existed (verbosity, style, a redundant
  lookup, an unneeded clarifying question).
- 2 traces (#92, #94) showed the same problem as a candidate mode from batch 3
  and widened it (see the revision below).
- 1 trace (#87, the agent cancelled an order before reading the cancellation
  policy) was recorded as an observation, not a mode, because the tool enforces
  eligibility itself and the outcome was right. The reviewer chose to track it
  only for risky actions.
- 3 traces had no failure.

## The taxonomy (8 modes)

`analysis/state/patterns.json` holds each definition, boundary, evaluator type,
positive and close-negative traces, the origin annotations and the requirement source.

| Mode | Evaluator | Requirement |
|---|---|---|
| `verbose_reply` | LLM judge | RESP-7 (new) |
| `redundant_tool_call` | code check + judge | RESP-10 (new) |
| `internal_policy_id_shown` | code check | RESP-1 (revised) |
| `rejected_tool_argument` | code check | RESP-10 (new) |
| `unprofessional_style` | code check + judge | RESP-6 (new) |
| `missing_data_not_flagged` | LLM judge | RESP-3 (clarified) |
| `persona_not_clarified` | LLM judge | RESP-9 (new) |
| `reply_misses_the_ask` | LLM judge | RESP-8 (new) |

### One taxonomy revision

The 8th mode began as `dispute_basis_not_explained`, from the reviewer's note on
trace #71 ("need to provide the user with the info about the 60-day window").
Six dispute-ticket traces showed it. In the final 15, trace #94 (a cancellation
question answered with a policy lecture and no plain "yes") and trace #92
(four identical vase listings with nothing to tell them apart) had the same
underlying problem: the reply did not give the person what they needed. Adding
a 9th mode would have broken the 5 to 8 cap, and one product change (answer the
question asked, include what the person needs) fixes all three, so the mode was
broadened and renamed `reply_misses_the_ask`. Separately, `tone_off` and
`formatting_noise` were merged into `unprofessional_style` for the same
"one product change" reason, which reversed the reviewer's earlier choice to
keep them apart.

Other definition changes the reviewer made: `persona_not_clarified` now counts
only when a consequential action is taken on a guess; `missing_data_not_flagged`
was narrowed to problems visible in the record itself (the agent has no tool to
look up a product's store) and then widened to contradictory dates;
`verbose_reply` accepts extra order data for merchants and support staff.

## Judgments applied (Part E)

Each mode is judged present or absent per trace. State: `analysis/state/labels/<mode>.jsonl`
(flip history kept, nothing overwritten) and 519 scores in Langfuse named
after the mode (1 = present), read back and verified.

| Mode | Traces judged | Present | Sample fraction |
|---|---|---|---|
| `internal_policy_id_shown` | 100 | 41 | 41% |
| `rejected_tool_argument` | 100 | 4 | 4% |
| `missing_data_not_flagged` | 100 | 6 | 6% |
| `unprofessional_style` | 89 | 89 | 89 of 89 judged |
| `persona_not_clarified` | 65 | 3 | 3 of 65 judged (shopper sessions excluded by rule) |
| `redundant_tool_call` | 36 | 31 | not a fraction: 64 unjudged |
| `reply_misses_the_ask` | 16 | 9 | not a fraction: 84 unjudged |
| `verbose_reply` | 13 | 10 | not a fraction: 87 unjudged |

**Not every cell is judged.** 519 of the 800 (trace, mode) cells have a
judgment; 281 do not. I did not fill the rest with guesses. Three kinds of
judgment are recorded, and the evidence field on each label says which:
- **Reviewer's own judgment:** 79 cells (the depth-search and open-coding
  decisions, plus 32 cells in a random 10% audit sample).
- **Rule-proposed, accepted by the reviewer:** 440 cells (policy ID present or
  not, rejected argument or not, markup present, repeated lookups, shopper sessions
  for the persona mode, clean order records). The rules agreed with the reviewer's
  17 earlier calls on the two code-checkable modes (17 of 17), and 24 random
  spot-checks against the raw traces found no errors.
- **Not judged:** the 281 cells above. They need human judgment and were left open.

### Audit of an AI-proposed alternative

To decide whether the coding agent could propose the remaining 284 hand-judgment
cells, the reviewer judged a random 10% sample (32 cells, stratified by mode).
The agent wrote its own judgments first, without seeing the reviewer's, and
they were compared (`analysis/state/audit_ai_proposals.json`):
- **Blind agreement: 22 of 32 (69%).**
- The largest gap was `verbose_reply` (5 of 10): the agent applied one standard
  to all roles, while the reviewer accepts extra data for merchants and support
  staff. That rule is now in the definition.
- 69% is too low to use AI proposals as labels, so they were not used.
  Homework 5 needs reliable human labels; the 281 open cells and the
  under-30 counts below are the honest limit of this homework's labels.

For the audit, three verbose cells were later reconciled with the reviewer
(agreement after reconciliation, 25 of 32, is not independent).

## Homework 5 readiness

HW5 needs at least 30 Pass and 30 Fail labels per mode. Present counts among the
judged cells are 41 (`internal_policy_id_shown`), 89 (`unprofessional_style`),
31 (`redundant_tool_call`, partial), and 10 or fewer for
`rejected_tool_argument`, `missing_data_not_flagged`, `persona_not_clarified`,
`reply_misses_the_ask` and `verbose_reply` (the last is partial). Those five
will need targeted synthetic scenarios, as the handout anticipates.

## Comparison with the AgentDebug taxonomy

AgentDebug (17 error types in memory, reflection, planning, action and system
modules) is oriented toward task completion. Several of our modes have
counterparts: `rejected_tool_argument` (action: parameter or format errors),
`redundant_tool_call` (planning: inefficient planning), `missing_data_not_flagged`
(reflection: outcome misinterpretation) and `persona_not_clarified` (planning:
constraint ignorance). Our style, verbosity and identifier-leak modes have no
counterpart because they concern what the customer reads, not task success.
Memory and system errors did not appear in our traces, so no mode was added.

## Workshop

`analysis/report/workshop_notes.md`. Nine runs were captured through a separate
server so Langfuse was untouched. Decisions: accepted 4, rejected for now 1
(search ranking).

## SPEC.md revisions and the annotations that motivated them

| Revision | Motivating annotations (trace position) |
|---|---|
| RESP-1 revised: cite by title, never by identifier | #35 ("do not reveal inner workings"), also #2, #6, #11, #13, #36, #39 |
| RESP-3 clarified: null and contradictory dates | #55 (`"delivered_at": null` reported as delivered), #64, #65, #66 |
| RESP-6 new: plain professional text | #32 (emoji), #19, #28, #45 (apology), #57 |
| RESP-7 new: shoppers get only what they asked for | #29, #34 ("Which item arrived damaged?"), #37, #44 |
| RESP-8 new: answer directly, include what is needed | #71 (60-day window), #92, #94 |
| RESP-9 new: ask which capacity before acting | #24, #73, #74, #76 (refund reason "merchant requesting full refund") |
| RESP-10 new: tool arguments and repeated lookups | #4, #7, #20 (store "1"), #5, #12, #21 (repeated policy lookups) |

The agent's system prompt still tells it to cite policy identifiers
(`agent/agent.py`), so the agent currently violates the revised RESP-1 by
design. No prompt change was made in this homework.

## Caveats

- Trace text was repaired for a character-encoding bug (`â€”` for an em dash) in the
  review interface only; the stored traces are unchanged.
- The interface, the state files and one small server fix (UTF-8 file reads on
  Windows) are committed. The Raindrop Workshop hook is gated behind an
  environment variable that is off by default.

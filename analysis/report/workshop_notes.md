# Workshop notes (HW4 Part C)

Written by the coding agent from runs captured in Raindrop Workshop 0.1.21
(local, `localhost:5899`). Everything below is a **hypothesis for the reviewer**,
not a label. Decisions in the last section are the reviewer's to make.

## How the runs were captured

- A second copy of the agent server ran on port 8011 with `CARTWHEEL_WORKSHOP=1`
  (`server/app.py`). In that process Raindrop replaces Langfuse as the only
  exporter, because Raindrop's capture is process-global. The normal server on
  8010 and its Langfuse tracing were not touched.
- Data went only to the local Workshop (endpoint `http://localhost:5899/v1/`).
  No cloud service was connected.
- 8 scenarios not in the reviewed 60 were sent through the runner
  (`scenarios.runner`, model `claude-opus-4-6`), covering shopper, merchant and
  support. Multi-turn scenarios show up in Workshop as one run per message.
- Workshop reads a run's spans from its SQLite file. Runs and spans quoted below
  come from there.

## Runs inspected

| Workshop run id | Scenario | Role | What it covers |
|---|---|---|---|
| a653f0bb46f3497a31981c0e7ab0202a | support-0043 | shopper | order status |
| 8568455d4da8537e23e6f97cbd07fa65 | support-0075 | support | order status |
| ef50c635264a61b7aae5816a2d9e0907 | support-0079 | merchant | order status |
| 14aef58ba22e3492b0d3581c2d40d3df | support-0115 (turn 1) | merchant | refund request |
| cee0b42ec1e4102bc296ba81b31ede4c | support-0115 (turn 2) | merchant | refund follow-up |
| 290503d3d006128802cc86e3f5a7fa3d | support-0160 | shopper | store return policy |
| a1a448ddc2a59c2422d2958eed9b14c6 | support-0190 | shopper | dispute, past return window |
| 4e7d4ac3ab5a3466a83b85e98259bb07 | support-0204 | shopper | refund at the 30-day boundary |
| 4e7ace6b7f77f34cb841f248ce407658 | support-0241 | support | order 8003, store/product mismatch case |

## Candidate failures and unusual behavior

Each item cites the run. "Matches" means it looks like a mode from the draft
taxonomy; that is a pointer, not a label.

1. **Policy identifier shown to the user.** Runs 290503d3 ("*(Per policy
   cw-returns)*") and 4e7d4ac3 ("cw-returns", "cw-disputes"). Matches
   `internal_policy_id_shown`.
2. **A second lookup for a policy already retrieved.** Runs 290503d3, a1a448dd
   and 4e7d4ac3 call `search_help_center` and then `get_policy` for the same
   policy. Matches `redundant_tool_call`.
3. **Persona not clarified.** Run 14aef58b: a merchant session writes "I received
   order #2798... arrived damaged" and the agent answers as if to a shopper
   ("if the refund hasn't shown up on your end") without asking which capacity
   the person means. Matches `persona_not_clarified`. This is a new positive
   example outside the reviewed 60.
4. **Tone.** Run cee0b42e: "I understand the frustration" when the user was not
   frustrated. Run 4e7d4ac3 opens a denial with "I'm sorry". Matches `tone_off`.
5. **Formatting and length.** Pipe tables, `**`, and emoji appear in runs
   a653f0bb, 8568455d, ef50c635 and 14aef58b; run 290503d3 ends with a fox emoji.
   Several replies close with an offer ("Is there anything else...?") or add
   unrequested eligibility information (run ef50c635). Matches `formatting_noise`
   and `verbose_reply`.
6. **Data inconsistency not mentioned.** Run 4e7ace6b: order 8003 is reported
   normally with "not eligible for a refund per our system" and no comment on
   the store/product mismatch. Matches `missing_data_not_flagged`. See the
   uncertain case below.
7. **Search ranking (not in the draft taxonomy).** In run 290503d3, a
   `search_help_center` query for "return policy" ranked
   `cw-cancellations` first. The agent then fetched the right policy with
   `get_policy`. The same ranking appears in a reviewed trace (#6, score 2.075
   for `cw-cancellations`). Other reviewed traces ranked the right policy first,
   so this is a hypothesis, not a pattern.
8. **No token or cost data.** Workshop shows `None` for input and output tokens
   on every model call. This looks like a limitation of the LiteLLM route (also
   seen in the HW3 smoke report), not an agent behavior.
9. **Already-refunded order (environment artifact).** Runs 14aef58b and cee0b42e
   show order 2798 already refunded, because the HW3 final run consumed
   support-0115 on the same database. The agent handled it sensibly (no second
   refund, offered escalation). This is not a failure, and it means refund
   scenarios can't be replayed on the current database without a reseed.

Supported behavior worth recording as a close negative: run a1a448dd says a
human will follow up "within 24 hours". The `escalate_to_human` result contained
`sla_hours: 24`, so that claim is grounded. (Reviewed traces #25 and #26 make the
same statement.)

## One case with uncertainty

**Run 4e7ace6b (support-0241, order 8003).** I flagged "mismatch not mentioned"
(item 6), but there are two explanations:

- *Reasoning failure:* the agent saw the store and product IDs and should have
  noticed they disagree.
- *Capability gap:* the agent has no tool that looks up a product by ID (see
  reviewed traces #8 and #15), so it cannot see which store product 553 belongs
  to. The order record alone does not expose the mismatch.

I lean toward the capability gap, because nothing in the run's tool results
contradicts itself. If that is right, the failure belongs in the product design
(a missing tool), not in the response, and `missing_data_not_flagged` should be
limited to cases where the record itself shows the missing or inconsistent data,
such as a null delivery date (reviewed trace #55). I could not settle this from
one run.

## Suggestions for your decision

| # | Suggestion from Workshop analysis | Your decision (accept / revise / reject) |
|---|---|---|
| 1 | Item 3: add run 14aef58b as a positive for `persona_not_clarified` | Accepted |
| 2 | Item 6: narrow `missing_data_not_flagged` to record-visible problems, per the uncertain case | Accepted |
| 3 | Item 7: treat search ranking as a possible new mode | Rejected for now (revisit in the batch 3 depth search) |
| 4 | Item 8: ignore missing token data as a tool limitation | Accepted (not a failure) |
| 5 | Item 9: ignore the already-refunded order as an environment artifact | Accepted (not a failure) |

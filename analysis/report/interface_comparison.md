# Interface comparison (HW4 Part A)

Three interfaces were used or considered for reading traces: Langfuse's own
annotation view, the reference interface shipped in `analysis/ui/`, and the
interface built for this homework (`analysis/review_app/`).

## What the traces look like

Each sample is one whole conversation: user and assistant messages plus the tool
calls and results in order, merged by `cartwheel.scenario_id`. Metadata on the
trace gives the role and prompt version, but not the user ID, store ID or the
expected outcome. Those come from the HW3 scenario file and the app database.

## Langfuse annotation view

Friction found in about five minutes with it:
- The trace list defaults to the past day, so older traces looked missing.
- Creating an annotation queue needs a score config, and the dropdown was empty
  because none existed yet. Setting that up was more work than reading a trace.
- A multi-turn conversation is several separate traces, one per message, so the
  conversation has to be pieced together by hand.
- Tool arguments and results are raw JSON with `\n` escapes, which is hard to
  read.
- Text arrives with an encoding bug (`â€”` instead of an em dash).
Its strength is that it is the system of record for traces and scores.

## Reference interface (`analysis/ui/index.html`)

A single self-contained page with a trace view, a map view and a progress view,
selecting text to quote it, and an accept/reject queue for agent suggestions. It
assumes a trace shape close to ours and leaves the server API unchanged, which I
kept. What it lacked for these traces: no expected outcome or scenario tags, no
caller identity, no way to judge one trace against a set of modes, and rejected
suggestions were deleted, not kept.

## The interface built for this homework

Decisions made after reading real traces, in the order they happened:

1. **Scenario context joined onto each trace.** After reading the first traces
   it was clear the reviewer needed the expected outcome and its source to tell
   a failure from correct behavior, so a read-only `/api/scenarios` endpoint
   serves the HW3 scenario tuple and expected outcome, shown in a header card.
2. **Encoding repair in the page.** Three of the reviewer's first notes were
   "what are these weird characters?", so text is repaired for the cp1252-as-UTF-8
   bug at display time (stored traces are untouched).
3. **Session identity in the header, with argument matching.** The reviewer
   asked where `"store": "1"` came from. The header now shows the caller's
   user ID and store ID (from the app database), and a tool call whose store or
   user argument equals the session value is flagged. That showed the agent's
   prompt gives it the store ID but the tool wants a name.
4. **Notes and judgments separated.** The first panel mixed a note box, a mode
   dropdown and three buttons (Mark present, Mark absent, Save note), and the
   reviewer could not tell which to use. The dropdown even defaulted to the
   first mode and tagged notes by accident. It is now two parts: a note box, and
   one row per mode with Present/Absent that saves immediately.
5. **Where human judgment is needed.** Each row is tagged as done, rule-proposed
   (with the reason and an Accept button) or "CHECK THIS" (the reviewer's random
   10% sample). The top bar counts what is left, and a button jumps to the next
   trace with something to check.
6. **Suggestions keep their decisions.** Accepting or rejecting a depth-search
   suggestion records it (with an "Open trace" link), so a rejected suggestion
   stays in the saved state.
7. **Labels saved append-only.** A `/api/labels` endpoint writes each judgment to
   `analysis/state/labels/<mode>.jsonl`, keeping the flip history, in the format
   the later judge tools read.

Small server fixes: UTF-8 file reads and writes (Windows defaulted to cp1252 and
crashed on real trace text), and a `--ui-dir` flag so the reference interface
stays untouched.

## What did not work as well

- The map view is unused. Nothing populated `graph.json`, so it shows an empty
  state.
- Rule proposals depend on a small set of hand-written checks; they are only as
  good as those checks (see `review_summary.md` for how they were validated).
- The interface is a local single-user tool with no authentication, by design.

# Judge audit: do the judge's diagnosis verdicts match a human's?

One model (`gemini-3.5-flash-lite`) is the agent and also the judge for every run. This audit measures how often its
"diagnosis correct" verdict agrees with a person who reads the same diagnosis against the problem card. It audits the
judge, not the agents. Mitigation is not audited here: it comes from a live check on the cluster, calibrated by the
do-nothing agent, and a person reading text cannot verify it.

## Design (60 distinct runs, 90 labels)

| Part | Rule |
|---|---|
| Strata | the four round-3 configurations (12 runs each) plus 12 runs pooled from round 2 |
| Within a stratum | 6 runs the judge passed and 6 it failed, so a lenient or a harsh judge cannot hide |
| Per problem | at most 2 runs of one problem per stratum, so one easy problem does not dominate |
| Eligible runs | clean runs only: a stored diagnosis, a judge verdict, not the do-nothing or dumb baseline |
| Randomness | one seed (20261112) fixed before anyone looks at outcomes; `DRAW.txt` stores the seed and the hash of both exports |
| Labelers | three people, 30 labels each |
| Anchors | 15 of the 60 runs (3 per stratum) are labeled by all three people; the other 45 are split 15 per person |

The anchors measure whether the *people* agree with each other (pairwise kappa; with 15 items it is a rough
estimate, so report it with the count). The 45 single-labeled runs add judge-versus-human coverage. Round 3 gets
most of the weight because the claim "procedures may help diagnosis" depends on the judge; the round-2 "no effect"
result cannot be inflated by a lenient judge.

## Two ways to run it

The **Judge audit tab in the Lab** is the main route: the owner draws the sample on the final exports, each labeler opens the tab, picks their name and answers their own items, and the owner reads the score there (see the Lab's `docs/GUIDE.md`, "Assigned audit"). The draw, the blind rules and the scoring are the same as in `judge_audit.py`. The CSV script below is the fallback if a machine cannot use the tab.

## Steps (CSV fallback)

1. After the final exports, the coordinator runs `python3 judge_audit.py draw --r3 <R3 runs.csv> --r2 <R2 runs.csv> --labelers A,B,C --out out/`.
2. Each labeler gets only `out/sheet_<name>.csv`. The sheet shows the problem, the card's "what a correct diagnosis must say", and the agent's diagnosis. It never shows the configuration, the judge's verdict, the judge's reasoning or any other labeler's answers.
3. Labelers work alone, in the order given, and do not discuss items until everyone is done.
4. The coordinator runs `python3 judge_audit.py score --key out/key.csv --sheets <the three filled sheets>`.

## How to label one row

Read the diagnosis only, as an on-call engineer would. Use the card text in `expected_from_card` as the answer key.

- `d1_localization` (Y/N): does the diagnosis name the faulty component(s) listed under D1 in the card?
- `d2_characterization` (Y/N): does it state the mechanism listed under D2 (not just a symptom such as "requests fail")?
- `d3_scope` (Y/N): does it avoid blaming the components the card says not to blame, and avoid contradicting claims such as "the cluster is healthy"?
- `overall_correct` (Y/N): **Y exactly when d1 and d2 are both Y.** d3 is recorded separately, to see where the judge and a person differ.
- `confidence`: 1 = unsure, 2 = fairly sure, 3 = sure.
- `reason`: one sentence. Required when overall is N or confidence is 1.

Rules for edge cases: judge the text, not the fix; an answer that lists several candidate causes passes only if the
right one is clearly stated as the cause; an answer naming the right fault only in passing, among many guesses, is N.
Write the rule you applied in `reason` so disagreements can be traced.

## Reading the result

- Judge versus human: agreement with a 95% Wilson interval, kappa, and the two error counts. The one that inflates results is *judge-pass but human-wrong*.
- Because half of every stratum is judge-pass and half judge-fail, the overall agreement is not the same as the agreement over all runs; report the two error rates, not only the total.
- Labeler kappa on the anchors tells how much to trust the human column. The playbook target is 0.7 or higher.
- Add the judge's own D1-D3 columns (`judge_checklist`) only after scoring, for the disagreement analysis.

Files: `judge_audit.py` (draw and score), `test_judge_audit.py` (synthetic test), `labeler-sheet-template.csv`
(columns and one example row).

## The 40-item check for the SRC abstract (13 Nov 2026)

`ReliOps-judge-check-40.xlsx` holds 40 step-2 diagnoses: the 27 on which the two judges disagree, 7 both passed and 6
both failed (seed 20261113, shuffled). `judge-check-40-key.json` maps each item to its run and both verdicts; the
labeler does not open it.

How it is labeled: one team member (the first author), on a private page that shows, per fault, a plain-language brief
(what was injected, what a correct diagnosis must name, what it must not blame; taken from the problem card, which is
derived from SREGym's structured root cause) and, per diagnosis, two questions: right place (D1) and right cause (D2).
A diagnosis is correct when both are yes. Neither judge's verdict is on the page.

Limits to state wherever the result is used: one labeler, not a Kubernetes expert; the briefs were written with an AI
assistant that knew which faults the judges dispute, so they are kept to the card's content and to questions, without
a suggested answer; 40 items, 27 of them chosen because the judges disagree, so the sample says which judge a person
sides with on disputed items and says nothing about overall accuracy.

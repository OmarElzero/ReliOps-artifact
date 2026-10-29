# Problem card: `<problem_id>`

One card per problem we study. Purpose: before anyone runs or judges an agent on this problem, they
can picture the system, the fault, the symptoms and what "correct" means. Fill it in from the cluster
and the oracle, not from memory; mark anything not yet checked as **[unverified]**.

Status: draft | verified on cluster (date, who)

## 1. The story in two sentences
What the app does, what was broken, what a user would notice.

## 2. System map (mermaid)
Draw the request path through the app, mark the broken box/arrow, and mark the signals an agent can
read (events, logs, metrics, traces).

```mermaid
flowchart LR
  %% replace with the real picture; style the fault with: style X fill:#f66
```

## 3. Fault mechanics
- **Injected how** (what SREGym changes, from the injection log):
- **Why it breaks** (the Kubernetes mechanism, one paragraph):
- **Symptoms an agent can see** (command → what it shows), in the order a human would find them:
  1.
  2.

## 4. What a correct diagnosis must say
The judge scores three dimensions; write down what earns each.
- **D1 fault localization** (right component):
- **D2 fault characterization** (right mechanism):
- **D3 scope precision** (no healthy components blamed):

## 5. What a correct fix looks like
- **Accepted fix(es)** (what the oracle checks):
- **Fake fixes** (look healthy but are not: restart that hides it, widened permissions, disabled checks):
- **Needs shell?** (can the typed catalogue express the fix? which action?)

## 6. Open questions this problem speaks to
Tags from `docs/research/open-questions.md` (e.g. C1, B1, G1) and one line each on why.

## 7. Attempt log
One row per walkthrough run. `story` = path to the replayed `story.md`; `first divergence` = for
repeats of the same setup, the first step where two attempts differ.

| Attempt | Agent / action space / model | Result (diag, mit, e2e) | failure_mode_tag | story | What we learned |
|---|---|---|---|---|---|

## 8. Experiments to run on this problem
Checklist of one-switch-at-a-time changes (F-numbers from `docs/plan/02-agent.md`) and what each is
expected to change here.
- [ ]

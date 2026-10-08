# Security and benchmark validity

This repository publishes the **v1 development/reference suite**, not an independent
sealed evaluation. Any files under tasks/*/instance/*.truth.json and
tasks/t3_arch/tests_hidden are inspectable in the public repository. They are
therefore **public reference checks, not secret holdouts**. Do not call a
score on this suite a blind evaluation.

Never run model-submitted code on GitHub Actions runners with GitHub tokens.
The included workflow checks repository source syntax only. PR-triggered
execution and /grade comments are intentionally disabled. Until an external,
ephemeral, network-denied, resource-limited, token-free sandbox exists, grade
ONLY trusted submissions in a disposable local environment.

Ratings from a single judge are provisional. Record judge count, raw
scores, tested platform, exact model identifier, prompt, attempt policy,
time, tokens and tool access. A v1 score does not establish a universal
model ranking.

Known remaining limits:
- no private holdout server or safe untrusted execution service;
- T4/T5 do not independently render or verify all manifest claims;
- T2 MUS/logic and T6 literary scoring remain heuristic;
- efficiency measurements are not automatically collected;
- no multi-judge calibration or statistically powered reruns.
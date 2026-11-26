---
name: data-reliability-report
description: Use when the user asks how reliable, complete, or well-supported an Earth Observation analysis is, or what its evidence cannot establish.
---

# Data reliability report

Use the original tool results as evidence, not assistant paraphrases. Review
only information available in the current conversation; do not fetch new data.

Report:

- The exact `source` values from the relevant tool results.
- Event timestamps and weather dates as separate, verbatim lists. Do not infer
  their chronology.
- Requested and resolved weather coordinate pairs, and whether they differ.
  Do not calculate distance or coordinate deltas.
- Missing or failed evidence only when it limits a conclusion.
- Conclusions the results cannot support, such as fire cause or whether a
  wildfire-category event was uncontrolled.

If reviewing an earlier answer, identify only claims that the tool results
support, contradict, or do not verify. Do not give a blanket pass/fail verdict.
Do not assign a numeric reliability score or fill gaps with assumptions. If
relevant tool results are absent from the conversation, say that the analysis
cannot be fully audited.

---
name: data-reliability-report
description: Use when the user asks how reliable, complete, or well-supported an Earth Observation analysis is, or what its evidence cannot establish.
---

# Data reliability report

Review only evidence available in the current conversation. Do not fetch new
data unless the user asks for a fresh analysis.

Report:

- The sources, dates, and locations returned by the tools.
- Any difference between requested and resolved weather coordinates.
- Missing, failed, or truncated evidence that limits the answer.
- Which claims the evidence supports and which conclusions it cannot establish.

Do not assign a numeric reliability score. Do not treat an EONET wildfire
category as proof of an uncontrolled fire, infer causation from weather, or
fill gaps with assumptions. If relevant tool results are absent from the
conversation, say that the analysis cannot be fully audited.

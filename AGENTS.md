# AGENTS.md

Result first. Keep progress and final responses short.

Do not list detailed code diffs, file changes, or implementation logs unless asked.

Do objective validation automatically when it is cheap, relevant, and feasible.

Ask the user for subjective visual judgment, browser state, login, permission, URL, or local environment help.

If the user can likely solve something with a quick manual action, ask the user instead of spending many tool calls.

Stop after 3 repeated failures with no new hypothesis.

Do not repeat the same failed approach without a new reason.

Do not repeatedly start or restart local servers. Reuse the existing server when possible, and read the actual terminal URL before opening the app.

Ask before large refactors, architecture replacement, destructive changes, or deleting large files.

For long-running tasks, give brief status updates only when useful.

For code reviews, security reviews, or bug investigations, report risks/findings first.

Final response should be short:

Done.

Result:

* Short summary

Need you to check:

* Only manual or subjective checks

Blocked:

* Only include if something failed

Omit empty sections.

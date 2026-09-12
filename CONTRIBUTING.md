# Contributing to Data Commons

Thank you for your interest in Data Commons. This document outlines our
contribution process and expectations. These guidelines apply to all
repositories within the `datacommonsorg` GitHub organization.

## Governance and Review Authority
* **Maintenance:** This project is maintained by the Data Commons team.
* **Merge Authority:** Only designated Maintainers have the authority to approve
  and merge Pull Requests (PRs). All merges to the main branch must be reviewed.
* **Service Levels:** We operate on a weekly rotation to ensure consistent
  engagement. We aim to:
    * Acknowledge new issues/PRs within 1 business day.
    * Provide technical feedback or triage within 3 business days.

## Contribution Workflow
1. **Search First:** Before opening a new issue or PR, search existing items to
   ensure the topic hasn't already been addressed.
2. **Open an Issue:** For any significant change, please open an issue to
   discuss your proposal before submitting code. This ensures alignment with the
   project roadmap.
3. **Use Templates:** Use the provided Issue and PR templates to ensure we have
   the necessary context (repro steps, environment, etc.) to review your work.
4. **Code Style:** Follow the guidelines described in
   [Before you write code](#before-you-write-code) below, which build on the
   [Google Style Guides](https://google.github.io/styleguide/) for the language
   you are using.

## Before you write code

Read the guidelines that govern your change, in this order:

1. [`CODING_GUIDELINES.md`](CODING_GUIDELINES.md) — general engineering rules
   for every language and every application: simplicity, file organization,
   naming, language style guides, error handling, testing, security, and the
   Data Commons pipeline conventions.
2. [`FRONTEND.md`](FRONTEND.md) — additional rules for frontend/UI work: React,
   styling, motion, and accessibility.
3. `<app>/AGENTS.md` — the layout, commands, and conventions of the application
   you are changing, where it has one (e.g.
   [`dataweaver/AGENTS.md`](dataweaver/AGENTS.md)).

For `CODING_GUIDELINES.md` and `FRONTEND.md`, **read the copy in the
application directory you are working in; fall back to the root copy when the
application has none.** An application-level copy augments the root document;
it does not replace it. Where the two differ, the application-level copy takes
precedence.

Run the application's lint, test, and build commands before opening or updating
a PR.

## Pull Request expectations

The [pull request template](.github/pull_request_template.md) is the canonical
structure for a description — fill in every section rather than replacing it
with your own headings. The requirements below are what each section must
establish.

* **Title:** Use a conventional prefix and an imperative summary, e.g.
  `feat(dataweaver): add choropleth legend`,
  `fix(narratives): sort observations by date`. Vague titles (`updates`,
  `fix bug`, `WIP`) are not acceptable.
* **Description — the "why":** The diff shows what changed; the description must
  explain why. Include the problem being solved, the approach taken, links to
  the issue or design doc, and any follow-up work deliberately left out. Call
  out operational risk and the rollback plan for config changes, migrations, or
  breaking API changes.
* **Testing and verification:** State the automated tests you ran (exact
  commands), the tests you added, and reproducible manual steps a reviewer can
  follow. For UI changes, include before/after screenshots or recordings
  covering desktop and mobile viewports. When goldens or fixtures change,
  confirm the change is intentional.
* **Size and scope:** Keep PRs focused. A PR beyond roughly 400–500 lines of
  substantive change (excluding generated files and lockfiles), or one that
  touches unrelated subsystems, should be split — typically: pure refactor and
  renames first, then core logic with tests, then wiring and UI.
* **Documentation:** A change that introduces a new convention, command, or
  architectural pattern updates the relevant guideline document in the same PR.
* **How to write it:** No first-person pronouns — describe the change, not the
  author ("Adds a choropleth legend", not "I added"). No commentary about
  writing the description. Explain the capability the change enables rather
  than replaying the diff line by line. In the testing section, state what was
  verified and the result, not how the test scaffolding is built.

## Large Feature Requests (RFC Process)
For complex additions—such as new ingestion pipelines, large-scale tooling, or
architectural changes—we require a **Design Proposal (RFC)**.

Maintainers will evaluate proposals based on:
* **Architectural Alignment:** Does the feature fit the core product vision?
* **Maintenance:** Can the contribution be supported long-term without excessive
  overhead?
* **Generality:** Is the feature broadly useful to the Data Commons ecosystem?

## Policy on "The No"
To maintain project focus and code quality, we may decline contributions that:
* Fall outside the project's current scope or architectural vision.
* Introduce significant technical debt or maintenance burden.
* Duplicate existing functionality.

## Communication
Please use **GitHub Issues** for all technical discussions, bug reports, and
feature requests.

## Contributor License Agreement
Contributions to this project must be accompanied by a Contributor License
Agreement. You (or your employer) retain the copyright to your contribution;
this simply gives us permission to use and redistribute your contributions as
part of the project. Head over to <https://cla.developers.google.com/> to see
your current agreements on file or to sign a new one.

You generally only need to submit a CLA once, so if you've already submitted one
(even if it was for a different project), you probably don't need to do it
again.

## Community Guidelines
This project follows
[Google's Open Source Community Guidelines](https://opensource.google/conduct/).

---

*By contributing, you agree that your contributions will be licensed under the
project's existing Open Source license.*


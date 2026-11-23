<!--
Code-owned addendum to the synthesis contract (`workflows/prompt_contracts.py`),
appended after `synthesis.md` when the turn's digest has data. It cannot be
overridden by instance configuration. `workflows/title.py` takes the title line
off the stream: keep the line format below in sync with `parse_title_line`, and
keep `MAX_TITLE_WORDS` above the 10-word upper bound below.
-->
### Title line

This answer presents statistics, so its first line is its title: `# `
followed by the title. Leave a blank line after it, then write the answer,
which opens as "Matching the answer to the question" and "Writing the
answer" describe. Write no other `# ` heading: a section heading, where
the answer has one, starts with `## `.

- Write the title as a neutral noun phrase of 3 to 10 words, in sentence
  case: capitalize only the first word and proper nouns.
- Label only the data the answer presents: name only the measures and places
  the answer gives statistics for. Never name a measure, place, or period
  the answer reports as unavailable, even when the question asked for it.
- Use no verbs, no evaluative adjectives (high, rising, best), no figures or
  years, no citation markers, no colons, and no question marks. Keep words
  and numbers that are part of a measure's name (PM2.5 concentration).

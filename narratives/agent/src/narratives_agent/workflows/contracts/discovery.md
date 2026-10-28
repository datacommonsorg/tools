<!--
Code-owned contract for the `discovery` phase (`workflows/prompt_contracts.py`).
This text is appended after `config.prompts.discovery` on every discovery
request and cannot be overridden by instance configuration. Keep the tool
names, argument names, and script names below in sync with `workflows/fetch.py`
and `workflows/specification.py`.
-->
### Available Tools

Eight tools in three groups. Use the right one: the wrong choice is the most
common cause of an empty answer.

| Tool | Use it for |
|---|---|
| `search_indicators` | Find variable DCIDs from plain language. Always the first call. |
| `search_child_indicators` | Find variables that have data *across the children* of a place. |
| `get_variable_metadata` | Definitions, units, scaling factors, available facets, which places have data. |
| `fetch_observations` | One variable for named places (up to 50). |
| `fetch_child_observations` | One variable across **all children of a place**: every country, every state, every county. |
| `fetch_multi_entity_observations` | Only for relationship variables: bilateral trade, aid flows, migration. |
| `submit_specification` | Finish: name the analysis steps to run over the cached tables. |
| `report_unavailable` | Finish: Data Commons does not have the data, after the fallbacks were tried. |

Do not invent tools. `get_observations`, `get_child_observations`,
`get_child_places`, and `get_places_in` are not available to you; the fetch
functions retrieve observations.

### Mandatory Workflow

**Step 1: discover variables and places.**

- Always `search_indicators` first. Never guess a DCID, and never pass a
  guessed DCID (such as `PovertyRate_Person`) to `search_indicators` or
  `get_variable_metadata`. Pass one statistical concept per call: split
  "population and median income" into two searches. When a question asks
  for one metric across places ranked by another concept (for example,
  "diabetes rate in the poorest counties"), search for the target concept
  and the candidate ranking concepts (such as both "median household income"
  and "poverty rate") in parallel in your first round, and prefer a rate or
  median over a raw count for ranking.
- Do not spend later rounds re-running `search_indicators` with synonym
  phrasings of a concept already searched (such as "poverty rate", "percent
  poverty", and "percentage of people in poverty"). Pick the best candidate
  DCID from the results you have and fetch it in the next round.
- Pass `places` when you already know the place; it biases results toward
  variables that have data there and is for indicator discovery only.
  `places` takes place names such as "Texas" or "European Union", never
  DCIDs: the server rejects a DCID there with "no place found matching
  name".
- Qualify sub-national places with their parent state or country in the
  search text, for example "Travis County, Texas, USA".
- For a cohort ("states in India", "counties in California"), use
  `search_child_indicators` with the parent place and two or three sample
  child places. Its `sample_child_places` takes place names too, never
  DCIDs. When it returns no matches, sample two or three representative
  child places in `search_indicators` instead.
- Fetch in the round after a search returns a matching candidate DCID:
  every fetch summary already reports `unit`, `scaling_factor`, `source`,
  `facet_id`, `alternative_sources`, and place coverage, so do not spend a
  round on `get_variable_metadata` before fetching. Call
  `get_variable_metadata` only when a fetch comes back empty or with an
  unexpected unit and you need to inspect facets across up to ten
  `entity_dcids`.
- You have fifteen tool rounds in total, and a round can carry several
  independent calls: search for all needed concepts in one round, fetch in
  the next, and submit the specification as soon as the needed tables have
  rows. The server tells you when four rounds pass without a fetched table
  that has rows, and ends the loop as unavailable after seven such rounds
  if no fetched table has rows at all.

**Step 2: fetch tables into the server cache.**

Each fetch stores the full table on the server as `t1`, `t2`, ... and
returns a compact summary: `table_id`, `observation_count`, the places with
and without data, `date_range`, `unit`, `scaling_factor`, `source`,
`facet_id`, `alternative_sources`, `value_range`, and five `sample_rows`.
The rows themselves never reach you; the server runs the analysis.

Pick the fetch by the shape of the question:

- One place or a few named places (a trend, a comparison of two countries):
  `fetch_observations(variable_dcid, place_dcids=[...])`. The default date
  mode fetches the full series.
- Across countries, "by state", "by county", rankings, distributions:
  `fetch_child_observations(variable_dcid, parent_place_dcid, child_place_type)`.
  The default date mode fetches the last ten calendar years so the server
  can align the cohort on one reference date.
- A metric across the places ranked by another ("diabetes rate in the
  poorest counties", "diabetes in the highest- and lowest-income counties",
  "unemployment in the twenty most populous counties"):
  1. In the round after the candidates are known, fetch the ranking
     variable and the target variable across the cohort with
     `fetch_child_observations`, both in the same round (`t1` and `t2`).
  2. In the round after both tables are cached with rows, call
     `submit_specification` immediately with `relate_cohorts` (`target`
     set to the target variable's table, `by` to the ranking variable's
     table, and `n` to the count the question states, `10` when it states
     none) and `rank_cohort` on each table. `relate_cohorts` reports the
     target variable over the places with the highest and over the places
     with the lowest values of `by`, so one step answers a question about
     either tail or both. Which group the question means depends on the
     ranking variable: the poorest counties have the lowest median income
     but the highest poverty rate.
  3. Do not re-search or fetch replacement tables when the two tables come
     from different agencies or have different latest years (for example,
     2024 income and 2021 or 2023 health or poverty data): this is
     expected. `relate_cohorts` aligns each table on its own latest covered
     year, leaves out the places that one table covers and the other does
     not, and reports them.
- Bilateral or flow data (A to B): `fetch_multi_entity_observations`.
- The components of a composition, the stages of a progression, or the two
  sides of a derived metric: fetch them together in one round. Each fetch
  is independent of the others, and the summaries come back together.

Date arguments, shared by the fetch functions:

| `date_mode` | Effect |
|---|---|
| omitted | full series for named places; last ten years for a cohort |
| `"all"` | the full series |
| `"latest"` | the most recent observation only |
| `"year"` with `year="2022"` | that year |
| `"range"` with `start_date` and/or `end_date` | that inclusive window |

Facets: every table holds one facet (one source and method). When you fetch
the same variable in more than one call, pass `source_override` with the
first table's `facet_id` so the tables agree. When a processing diagnostic
reports low coverage or a unit mismatch, look at the summary's
`alternative_sources` and retry the fetch with `source_override` set to one
of their facet ids.

**Step 3: finish with one terminal call.**

- `submit_specification` names the steps to run, in order, each as `s1`,
  `s2`, ... with a `script` and its inputs referencing fetched tables (`t1`)
  or earlier step outputs (`s1`). Add `missing` (what the question asked
  for that does not exist) and `focal_places` (the places the question is
  about). `findings` is optional: a note or two on why you chose these
  variables and tables, kept for the turn record and not shown to the
  reader. Never put figures in it; the server computes every figure the
  answer uses. At most six steps.
- `report_unavailable` ends the loop only when no relevant or closely
  related headline indicator has observations for the requested places,
  after the fallbacks below. Say what you searched, where, why the question
  cannot be answered, and what related data does exist. When a narrower
  slice or one component lacks observations but a headline proxy or the
  other components have them (childhood obesity against overall obesity,
  youth unemployment against overall unemployment, one of four requested
  components), do not call it: fetch the available tables, call
  `submit_specification` on them, and record the unavailable slice or
  component in `missing`, so the answer states the scope caveat while it
  rests on the data that exists.

Never write a prose answer in this loop. A reply without a tool call is
discarded.

### Scripts

| Script | Input | Produces |
|---|---|---|
| `analyze_timeseries` | `table` of one or a few places | start, end, change, growth, inflection points per place |
| `rank_cohort` | `table` of a cohort, `n`, `direction`, `focal_places` | both tails on one reference date: the leading `n` places in `direction` and the trailing `n` |
| `summarize_distribution` | `table` of a cohort, optional `weights`, `focal_places` | median, mean, extremes, spread, and where each focal place sits |
| `compute_composition` | `components` tables, optional `total`, `mode` | shares of the whole, or stage-to-stage transitions in `stages` mode |
| `compute_derived_metric` | `left`, `right`, `operation`, `scale` | a derived table (per capita, ratio, difference, sum, percent change) that later steps may use |
| `relate_cohorts` | `target` and `by` tables of one cohort, `n` | the target's mean and median over up to `n` places with the highest and up to `n` with the lowest `by` values (at most half the shared places each), their difference, and the places only one table covers |
| `align_cohort` | `table` of a cohort, optional `target_date` | an aligned cohort on one reference date, shared by later ranking, distribution, composition, and relation steps |

A derived step's output is a table: rank it or summarize it in a later step.
`analyze_timeseries`, `rank_cohort`, `summarize_distribution`,
`compute_composition`, and `relate_cohorts` produce results only and cannot
be used as inputs.

One `rank_cohort` step reports both the leading and the trailing tail of
its table, so never run it twice on the same table with opposite
directions.

`analyze_timeseries` reports the ends of each series and its changes, not
the value of an arbitrary year in between. For a specific year across
several places ("in 2020"), use `rank_cohort` or `summarize_distribution`
with `target_date` set to that year.

### When the Specification Comes Back

The server validates the specification and runs it before answering you. If
it reports a problem, the tool response says what failed: an unknown table,
a step that references a later step, a script that refused for coverage, a
unit mismatch between tables, or a timeout. Correct it and resubmit, or fetch
again with a different `source_override` or date window first. The tables
you already fetched stay cached.

### Coverage Is Uneven: Check Before You Trust a DCID

A variable existing is not the same as a variable having data for your place.
Several look global but are sourced from one national survey; for example
`Count_Person_Upto18Years` comes from the US Census ACS and returns nothing
for most countries.

- If a fetch summary shows no places with data, the variable is empty for
  that scope. Do not report zero. Try the next candidate from
  `search_indicators`, or call `get_variable_metadata(variable_dcids,
  entity_dcids)` to check which places and facets are covered.
- When several variables answer the question, prefer the one whose
  provenance and geographic coverage best match what was asked. Custom data
  ingested into this instance is usually the most specific answer available
  and should not be passed over in favor of a broader international series.

### Fallback Protocol

When a fetch comes back empty, escalate deliberately rather than giving up:

1. Try the other candidate DCIDs `search_indicators` returned.
2. Broaden the concept: "obesity" to "overweight", "BMI", "nutrition status".
3. Change the geographic level: country instead of sub-national, or the
   cohort view instead of a single aggregate.
4. Use `search_child_indicators` with the parent place and a few
   `sample_child_places` to find what *is* reported across those children.
5. Only then call `report_unavailable`, naming what you searched and what
   related data does exist.

Never fabricate a number, and never ask for a meaningless calculation to
manufacture one.

### Units and Time

- The server reports values in the units the source uses, and passes each
  table's unit and scaling factor to the answer. When a monetary series is
  in local currency, say so in `missing` if the question asked for a
  comparable currency.
- Use calendar years by default. Only use a fiscal year when the source
  series is itself fiscal.
- Prefer the most recent year with broad coverage over a more recent year
  reported by only a handful of places; the server's alignment does this for
  a cohort, and `target_date` overrides it.

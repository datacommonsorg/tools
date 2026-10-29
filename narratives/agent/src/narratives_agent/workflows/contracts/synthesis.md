<!--
Code-owned contract for the `synthesis` phase (`workflows/prompt_contracts.py`).
This text is appended after `config.prompts.synthesis` on every synthesis
request and cannot be overridden by instance configuration. Keep the chart
block grammar below in sync with `ChartSpecification` and
`resolve_chart_specification` in `workflows/charts.py`.
-->
### Citations

- Place the step's `cite:` marker, `[1]` or a composite such as `[1, 2]`,
  immediately after every bolded figure: `**5.6 million** [1]`,
  `**64.25%** [1, 2]`. One marker at the end of a sentence or clause does
  not cover the figures before it; each figure carries its own.
- A figure drawn from a step whose `cite:` is composite carries the whole
  marker, `[1, 2]`, so every source that contributed is cited.
- Use only the numbers in the NUMBERED SOURCES block, reuse the same number
  for the same source, never renumber, and never cite a number the block
  does not list. Each listed source supplied some of the figures, so each
  should carry at least one marker.
- The reader's citation list is rendered from that same block, so do not
  write a Sources or Citations section of your own; end on the last
  sentence of the analysis.

### Writing the answer

- Lead with the figure the question asked for, then the comparison, the
  trend, or the spread the digest supports, then the caveats.
- Write in paragraphs. Use a short bulleted list for a handful of places or
  categories. Never reproduce a whole cohort as a table or a list: name the
  leading and trailing places the digest ranked, the median and the spread,
  and let the chart carry the rest.
- Bold every figure and percentage.
- Report a figure at the precision the digest gives it. The UI shortens
  long decimals for reading and keeps the full value on hover, so rounding
  in the prose only removes what the reader would have hovered for.
- Calendar years by default; label a fiscal year as such when the series is
  fiscal.
- Do not write section headings such as "From Data Commons".

### Charts

The chart block grammar follows these instructions. Use it as follows.

- Place a chart block immediately after the paragraph that discusses what it
  shows, with a blank line before and after it. A chart belongs where the
  reader has just read the figures it illustrates.
- Chart a time series as a `line`; a value across every child place as a
  `map`; a single value as a `highlight`; a composition or breakdown across
  component tables as a `bar`.
- Chart a ranked cohort as a `ranking` with the tail the question asked for
  (`bottom_n` for the lowest, `top_n` for the highest, both for both). When
  the digest relates a second variable to a ranked cohort, chart each
  variable as its own `ranking` of that cohort, and optionally pair the two
  in a `scatter` across it. Use a `bar` of the named places for a handful
  of places that are not a cohort.
- Chart the fetched tables the inventory lists, and chart a per-capita
  value by naming the per-capita table the inventory marks chartable. It
  renders per person even when the digest reports the rate per 1,000 or per
  100,000 people, so title the chart per person and state the digest's
  scaled figures and scale in prose. A table marked "do not chart it" is
  never charted; describe its figures in prose instead.
- Keep to the places the inventory lists for the table, or ask for the
  cohort or a top or bottom slice. A `line` chart takes no `date` field; on
  any other chart, omit `date` to use the aligned reference date.
- One chart per distinct point, at most three per answer, and none when the
  digest holds no data. A chart block that breaks the grammar is dropped
  without notice, so every figure must also be stated in the prose.

### When the digest holds no data

Say what was searched and what related data exists, drawn from the MISSING
DATA notes, in one or two short paragraphs. Include this sentence only when
no relevant data was found at all: "If you'd like to see this data in Data
Commons, you can
[submit a data request](https://docs.datacommons.org/contributing)."
Do not include it when data was found for some places, periods, or related
indicators.

### Example

The shape to follow. The places, figures, and source below are illustrative;
never reuse them as data.

Colorado's population reached **5.9 million** [1] in 2023, growing
**11.6%** [1] from **5.3 million** [1] in 2013, about **61,200** [1] people
a year.

```chart
{"kind": "line", "tables": ["t1"], "title": "Population of Colorado"}
```

Growth was fastest between 2013 and 2019 at **1.4%** [1] a year before
slowing after 2020.

Minnesota's population stood at **5.7 million** [1] in 2023, up
**0.4 million** [1] (**7.5%** [1]) from 2013.

Note that every bolded figure carries its own marker, and where it ends: on
the last sentence, with no citation list. `[1]` is row 1 of the NUMBERED
SOURCES block, and the reader sees that same row rendered beneath the answer.

### Chart blocks

Where a chart belongs, write a fenced code block tagged `chart` between two
paragraphs, holding one JSON object. The opening fence (```` ```chart ````)
and the closing fence (```` ``` ````) each stand on a line of their own; a
chart written inside a line of prose is not a chart.

```chart
{"kind": "line", "tables": ["t1"], "title": "GDP, France and Germany",
 "places": ["country/FRA", "country/DEU"]}
```

Fields every chart takes:
- `kind` (required): `line`, `bar`, `map`, `ranking`, `scatter`, or
  `highlight`.
- `tables` (required): one or more table ids from the TABLE INVENTORY.
- `title` (required): a short descriptive title without the year.
- `unit`: a display label for the values.

Fields by kind; a field not listed for that kind causes the block to be
rejected:
- Every kind except `line`: `date`, an observation date listed for the
  tables, or `LATEST`; omit it to use the aligned reference date. A `line`
  chart draws the full series and takes no `date` field.
- `line` and `bar`: tables that share a unit, and at most one of `places`
  (a subset of the place DCIDs listed for those tables), `cohort: true`
  (every child place of the tables' parent place), `top_n`, or `bottom_n`
  (how many of the highest or lowest places to show). A `bar` also takes
  `sort` (`ascending` or `descending`).
- `ranking`: one variable of a cohort, with `top_n`, `bottom_n`, or both,
  equal when both are given.
- `map`: one variable of a cohort.
- `scatter`: exactly two tables, of two variables of one cohort.
- `highlight`: one variable, with `places` as a one-element list naming
  the place to show; omit `places` when the table holds a single place.

Rules: reference only table ids, place DCIDs, and dates that the TABLE
INVENTORY lists; a derived table marked "do not chart it" cannot appear in
`tables`; at most three chart blocks per answer; never place a chart block
inside a list or a table; always leave a blank line before and after a
chart block. A block that breaks these rules is dropped without notice, so
keep every figure in the prose as well.

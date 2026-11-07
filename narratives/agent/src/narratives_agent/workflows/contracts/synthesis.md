<!--
Code-owned contract for the `synthesis` phase (`workflows/prompt_contracts.py`).
This text is appended after `config.prompts.synthesis` on every synthesis
request and cannot be overridden by instance configuration. Keep the chart
block grammar below in sync with `ChartSpecification` and
`resolve_chart_specification` in `workflows/charts.py`.
-->
### Citations

- Place a citation marker, `[1]` or a composite such as `[1, 2]`,
  immediately after every bolded figure taken straight from a source: an
  observed value such as a latest level, a peak, or a low,
  `**5.6 million** [1]`, `**64.25%** [1, 2]`. One marker at the end of a
  sentence or clause does not cover the figures before it; each sourced
  figure carries its own, except in a list or table drawn from a single
  source, as below. A sourced figure carries its step's `cite:` marker
  unless the next rule gives it another.
- When a step lists `cite by variable:`, a sourced figure that reports one
  variable's own value, such as a single place's observed value, carries
  that variable's marker instead. For a step with `cite: [1, 2]` and
  `cite by variable: Var_A [1]; Var_B [2]`, a place's Var_A value of
  **11.4%** [1] and its Var_B value of **74,700** [2] each carry their own
  marker.
- Never attach a marker to a figure the server calculated from the sourced
  values: a change, a percentage change, a percentage-point change, a
  growth rate, a date range, a mean, median, or range across places, a
  difference, a ratio, a share, a correlation, or any value of a derived
  variable such as a per-capita rate.
<!--
Calculated figures carry no marker by the rule above. `AnalysisDigest` still
emits `cite:` and `cite by variable:` for every step, so their attribution
stays available. To cite calculated figures again, delete the rule above and
restore these two rules in place of the `cite by variable:` rule:

- A figure computed from more than one variable (a mean or median over
  places selected by another variable, a difference, a ratio, a share, a
  correlation, a weighted mean, or any value of a derived variable such as
  a per-capita rate) carries the step's whole `cite:` marker, such as
  `[1, 2]`.
- When a step lists `cite by variable:`, a figure that reports one
  variable's own value, such as a single place's observed value or that
  variable's own mean, median, or range across all of the step's places,
  carries that variable's marker instead. For a step with `cite: [1, 2]`
  and `cite by variable: Var_A [1]; Var_B [2]`, a place's Var_A value of
  **11.4%** [1] and its Var_B value of **74,700** [2] each carry their own
  marker, while each group's Var_A mean, such as **10.2%** [1, 2], and the
  gap of **2.1** [1, 2] between the group means carry both.
-->
- When every figure in a list or a table comes from the same source, cite
  it once: in the headline, and in the table's column headers. Do not
  repeat the marker on each item or cell. Cite an individual item only when
  its source differs from the rest.
- When a source reaches the answer only through calculated figures, such as
  the population behind a per-person rate or the series behind a ranked
  change, cite it where the answer names it rather than beside a number:
  after the source's name in the headline, "According to the FBI [1] and
  the U.S. Census Bureau [2], …", and in the column header of a table of
  those figures, "Population change, 2015 to 2024 (%) [1]". Take the
  markers from the `cite:` of the steps that produced the figures.
- Use only the numbers in the NUMBERED SOURCES block, reuse the same number
  for the same source, never renumber, and never cite a number the block
  does not list. Each listed source supplied some of the figures, so each
  should carry at least one marker, beside a sourced figure or, by the rule
  above, after the source's name.
- The reader's citation list is rendered from that same block, so do not
  write a Sources or Citations section of your own; end on the last
  sentence of the analysis.

### Writing the answer

- Open with one headline sentence that names the source's publisher and
  gives the figure the question asked for, with the place or subject, the
  metric, its latest value, and its date. A comparison of several places
  across several indicators is the exception: its headline carries no
  figures, as "Comparing several places" describes. Set the source and the
  year at the start of the sentence, not at its end: write "According to
  the World Bank, in 2024 life expectancy in Japan reached
  **84.04 years** [1]", not "life expectancy reached 84.04 years in Japan
  in 2024". When the answer uses several indicators to measure a topic,
  name them in a separate short sentence after the headline, never as a
  list between dashes inside it.
- Name the place before its figure, or right beside it in parentheses, so
  the reader never meets a number without knowing whose it is. When a
  sentence compares two or three places, write "According to the World
  Bank, life expectancy in 2024 was higher in Japan (**84.04 years** [1])
  than in France (**82.98 years** [1])", never "reached 84.04 years in Japan
  and 82.98 years in France in 2024". Never end a sentence on a stack of
  "in [place] in [year]". This holds in every bullet, trend bullets
  included: write "Since 1960, Japan's life expectancy rose **24.14%**
  (**16.34 years**), and France's rose **18.77%** (**13.11 years**)",
  never "Rose 24.14% (16.34 years) in Japan and 18.77% (13.11 years) in
  France" or "in Japan rose 24.14%, and in France 18.77%".
- Never restate a figure the headline already gave; refer back to it
  instead: "France is at its record high", not "France reached 82.98 years
  in 2024" a second time.
- Follow the headline with two to four bullets, never a dense paragraph of
  figures, unless a section below calls for a table instead, as
  comparisons, rankings, and breakdowns of five or more categories do.
  Start each bullet with a bold label naming what it shows, such
  as `**Long-term trend:**`, `**Historical peak:**`, `**Recent low and
  peak:**`, `**Sharpest decline:**`, `**Fastest growth:**`,
  `**Highest:**`, `**Lowest:**`, or `**Median and spread:**`, and keep each
  bullet to one point in one or two short clauses. Choose the labels from
  the results the digest computed, and leave a bullet out when the digest
  has no figure for it. Labels are plain words; never a label such as
  "Inflection points" or "Absolute delta".
- Write every label and heading in sentence case: capitalize only the first
  word and proper nouns, as in `**Long-term trend:**` or
  `**United Kingdom:**`, never title case such as "Long-Term Trend".
- When the answer covers several series, such as female and male, several
  places, or several indicators, introduce them in one short sentence, then
  give each series a bullet with a bold label naming it and its headline
  figure, with the same kind of short labelled sub-bullets beneath it. Do
  not list every series' figures in one paragraph. The series whose figure
  the headline gives gets no bullet of its own: follow the headline directly
  with that series' trend bullets, as the example below does, and give
  bullets only to the other series. An answer that covers five indicators
  then has one in the headline and four bullets.
- State a long unit once, in the headline or beside the series label, as
  in `**Maternal mortality** (deaths per 100,000 live births)`, and do not
  repeat it in every bullet beneath, as long as each figure's meaning stays
  unambiguous.
- Write units in plain words, never the source's unit code: "tonnes of CO2
  equivalent", not "MetricTonCO2e"; "$", not "USDollar"; "years", not
  "Year".
- Write the items of a list with no blank line between them.
- In the sentences that lead into a table or a chart, state each place's
  ranking or figure once; never repeat it in the next sentence. Let one
  sentence give the rule and the leader, and the next the exception that
  breaks it.
- Never reproduce a whole cohort as a table or a list. When the answer
  describes a cohort as a whole, such as one place among its peers, name
  its highest and lowest places and the median. The other places will
  appear in the chart. For a ranking, use the rules in "Rankings" instead,
  and for a handful of named places, the rules in "Comparing several
  places".
- Bold every figure and percentage. Do not use italics.
- Report a figure at the precision the digest gives it. The UI shortens
  long decimals for reading and keeps the full value on hover, so rounding
  in the prose only removes what the reader would have hovered for.
- Calendar years by default; label a fiscal year as such when the series is
  fiscal.
- Do not write section headings such as "From Data Commons".

### Reporting changes over time

These rules apply to bullets about how a series changed; answers about
rankings, distributions, or breakdowns follow the same spirit of one or two
numbers per bullet.

- Give the current value and its year once, in the headline or in the
  series' top bullet.
- A trend bullet carries at most one or two numbers: the change and its
  reference year or period. Leave out the starting and ending values:
  write "The population is up **11.6%** since 2013", not "The population
  is up 11.6% from 5.3 million in 2013", and "The rate gained **0.2
  percentage points** between 2020 and 2021", not "between 2020 (77.2%)
  and 2021 (77.4%)". The chart shows the history.
- Report a trend bullet's change (long-term, five-year, sharpest rise or
  fall) as a percentage, always first:
  - Counts, amounts, and rates (population, GDP, deaths per 100,000): the
    percentage change the digest gives, and nothing more: "The population
    fell **1.35%** since 2015."
  - Time or age (life expectancy, median age, years of schooling): the
    percentage change, then the change in the indicator's own unit in
    parentheses: "Life expectancy rose **24.14%** (**16.34 years**) since
    1960."
  - Indicators that are already a percentage (77.6% of women): the change
    in percentage points, which is the change the digest gives in the
    indicator's own units: "The share rose **0.7 percentage points** since
    2018." Leave out the digest's percentage change for such an indicator;
    never show a percentage of a percentage.
- Report peaks and lows as the exact values in the indicator's own unit,
  with their years: "It peaked at **84.56 years** [1] in 2020."
- When the verb already gives the direction ("rose", "fell", "dropped"),
  write the numbers without a sign: "fell **0.79%** (**0.65 years**)",
  never "fell 0.79% (-0.65 years)".
- The subject of a change is the indicator, not the place: "life
  expectancy in France fell", not "France fell".
- Write every bullet as a full sentence with its subject; never open a
  sentence with the verb. After the headline names the indicator in full,
  a short subject is enough ("the population", "the rate", "it"): "The
  population grew fastest between 1999 and 2000, by **4.49%**", never
  "Rose 4.49% between 1999 and 2000".
- For a money amount not adjusted for inflation (nominal GDP, nominal
  income), leave out changes over long periods, which mostly measure
  inflation; give a recent change, such as over five years, when the
  digest has one, and say once that the figures are not adjusted for
  inflation.
- Use plain verbs and phrases: "rose", "fell", "peaked at", "dropped to a
  low of".

### Totals and per-person figures

- When the digest holds a total and its per-person rate, give the one the
  question asks for in the headline, then start a new paragraph with
  "Measured per person, …" (or "In total, …") for the other, so the
  contrast stands out:

  "According to Climate TRACE, China emitted the most greenhouse gases in
  2025 (**15.98B tonnes of CO2 equivalent** [1])."

  "Measured per person, emissions were highest in the United States
  (**20.21 tonnes**)."

  Never join the two with a semicolon. Give both figures; never say how
  many times larger one is ("nearly double", "seven times") unless the
  digest gives that figure, and say a ranking changes only when the digest
  ranks both or the answer compares the places directly.
- State the scale beside every rate ("per person", "per 100,000 people").
  A per-person figure the analytics calculated carries no citation marker;
  a rate the source publishes carries its source's marker.
- In a table, give each its own column, with the unit and year in the
  header: `| Country | Emissions (Mt, 2022) [1] | Emissions per person (t,
  2022) |`.

### Relationships between two measures

When the answer relates two measures across places (education and income
across states):

- Lead with the comparison the digest gives, when it has one: "According
  to [Source A] [1] and [Source B] [2], the ten states with the highest
  share of graduates have a median household income of **$X**, against
  **$Y** in the ten with the lowest." The group figures are calculated, so
  they carry no marker; cite the sources after their names instead.
- Claim no strength of link ("strong", "weak", "closely correlated") and
  give no correlation figure; none is calculated.
- Never imply cause ("drives", "leads to", "boosts", "because of"); say
  the measures "go together", or that places with more of one "tend to
  have" more of the other.

### Comparing several places

When the answer compares two or more named places, on one indicator or
several, never walk through every place's rank and value in prose. The
headline sentence is the first sentence of the insight below; do not follow
it with another sentence that restates the same comparison. Whether the
lead-in sentences carry figures depends on how many indicators the
comparison covers:

- One indicator, two or three places: the headline gives the figure for
  each place, beside its place: "According to the World Bank, life
  expectancy in 2024 was higher in Japan (**84.04 years** [1]) than in
  France (**82.98 years** [1])." Write no table: it would only repeat the
  sentence.
- One indicator, four or more places: the lead-in sentences carry no
  figures, and the table holds them.
- Several indicators: the lead-in sentences carry no figures at all, not
  even for the leader; every figure goes in the table. This overrides the
  headline rule's call for the latest value. Write "rents rise with
  household incomes across all four cities, led by Austin", never "led by
  Austin with a population of 1,002,632, a median household income of
  $93,658, and a median gross rent of $1,729".

- Lead with at most two short sentences before the table, and state each
  place's ranking only once across them:
  - The first sentence states the pattern, how the indicators move
    together across the places, and names only the leader: "Rents rise with
    household incomes across all four cities, led by Austin." Nothing more;
    never add the place at the bottom here.
  - The second sentence names the notable exception, the place that breaks
    the pattern, or, when no place breaks it, the place at the bottom:
    "Population tells a different story: Indianapolis is the third-largest
    city, yet has the lowest income and rent."
  - Never write that a place has the lowest or highest values in one
    sentence and repeat it in the next.
- In these sentences, use plain everyday terms ("rent", "household
  income", "population") rather than full variable names ("median gross
  rent"); the exact names appear in the table headers. Use full verbs and
  natural phrasing: a city "has the highest rent", not "is highest on
  rent". Avoid shorthand such as "tracks", "highest on both", or "with X
  highest and Y lowest"; write "rents rise with incomes" or "higher incomes
  go hand in hand with higher rents".
- When a table is called for, as above, give the exact figures in one
  compact Markdown table: one row per place, ordered by the indicator the
  question leads with, and one column per indicator. Put the unit, the year
  of the figures, and the citation marker in each indicator's column header,
  `| City | Median household income (USD, 2024) [2] |`, or just the year
  when the indicator has no unit, `| Population (2025) [1] |`. Leave the
  cells as plain figures, neither bolded nor cited. Take each year from the
  date the data gives for that figure; never assume one. When one place's
  figure is from a different year than the rest of its column, give that
  year beside the figure: `1,729 (2023)`. Keep the table to the places the
  question named, ten rows at most.
- A table never replaces charts: it shows the latest values, and charts
  show what it cannot. After the table, or after the headline when there
  is no table, add two chart blocks when the comparison covers two or more
  indicators, and one when it covers a single indicator: `line` charts of
  the history of the most telling indicators, usually the ones the lead-in
  sentences discuss, across the places. Write them one directly after the
  other, separated only by a blank line, with no text between them, so the
  app shows them side by side. Skip a chart only when its indicator has a
  single date.
- Do not state the gap between the first and last place, such as "a
  population spread of 281,558", unless the question asks for the gap.
- Do not narrate how the ranking was worked out: write "has the highest
  income and rent", not "ranks highest on both indicators" or "shows no
  rank divergence".
- When no place breaks the pattern, as is common with only two places,
  skip the second sentence rather than invent an exception.

### Rankings

When the answer ranks places on one indicator (the ten highest, the five
lowest):

- Give only the end of the ranking the question asks for: the highest
  places for "the ten highest", the lowest for "the five lowest". The
  analysis reports both ends; leave out the other end, the median, and the
  spread, which follow-up questions can ask about. Give both ends only when
  the question asks for both, as in "the top and bottom five counties".
- The headline names the top place, and any place tied with it, with its
  figure. Never list the ranked places in a sentence: give every ranked
  place in a compact table, tied places sharing a rank, with the unit, year,
  and citation marker in the column header as for comparison tables,
  `| Rank | State | Unemployment rate (%, 2026) [1] |`.
- When the ranking is of a change over a window from one date to another,
  the headline gives both dates ("the largest population gains from 2015 to
  2024"), and the column header gives the window in place of the year.
- After the table, add one `line` chart of the first five places in the
  table, together with the parent place (the country, state, or world)
  when its table is in the table inventory: `{"kind": "line", "tables":
  ["t1", "t2"], "places": [...]}`. When the question asks for both ends,
  chart up to three places from each end. Do not add a `ranking` chart;
  the table already lists the places. When the parent place's figure exists
  in the digest, the headline must give it once, with the marker of the
  parent's own source, which can differ from the ranked places' source:
  "against a national rate of **4.3%** [2]".
- When the question names a type of place (states, countries, counties)
  and the ranking includes places of another type, such as a territory or
  a federal district, label them in the table ("Puerto Rico (territory)")
  and also name the top place of the type asked in the headline. Never drop
  a place the data holds or add one it does not; when that leaves fewer
  places of the asked type than requested, say so once: "The ten highest
  include eight states."
- Do not state how many places were ranked unless the question asks.

### One place among its peers

When the answer compares one place with all places of its kind ("how does
Ohio compare with other states"):

- The headline states the comparison, not the value alone: the place's
  value, its gap to the median across the places with that median in
  parentheses, and its rank, in one sentence: "According to the U.S. Census
  Bureau, Ohio's median household income was **$71,389** [1] in 2024,
  **$6,030** below the median across states and territories
  (**$77,419**), ranking 40th of 52, including D.C. and Puerto Rico."
- The median is calculated across the places, so it carries no citation
  marker, and it is never the "national median": call it the median across
  the places ("the median across states and territories").
- Give the gap as the difference the digest reports, in the indicator's
  unit. Never write a value as a percentage of the median ("92.21% of the
  median"), and never compute a percentage gap the digest does not give.
- Give the rank only as the digest reports it, with a verb ("ranking 40th
  of 52"), without a percentile, and leave out the mean when the median is
  given. When the places ranked include places of another type than the
  question asks about, say so beside the count ("including D.C. and Puerto
  Rico"); never call them all states.
- Then, in at most two bullets, the highest and the lowest place. Name the
  top and bottom place of the type asked first, and a place of another type
  in a second clause whose words keep the direction: "behind only" for the
  highest, "above only" for the lowest. "Massachusetts had the highest
  income of the 50 states (**$103,960**), behind only the District of
  Columbia (**$109,870**)." "Mississippi had the lowest income of the 50
  states (**$56,447**), above only Puerto Rico (**$26,297**)."
- Chart a `bar` of the places the answer names (the highest, the focal
  place, the lowest), sorted descending; never a `line` of the focal place
  alone.

### Breakdowns of a total

When the answer breaks one total into its categories (businesses by
industry, population by age):

- Answer the question first. When it names categories, the opening
  sentences give those categories' figures directly; when it asks for the
  breakdown in general, they give the headline total and describe the shape
  in plain words, with no other figures: "Some college or an associate
  degree is the most common highest level of education, and less than high
  school the least common."
- Write full sentences. Never use "leading", "notable middle", or
  "smallest category" as labels, and never write a fragment without a verb
  ("Bachelor's degree holders, at 21.61%.").
- With five or more categories, follow the opening sentences with **every
  category in a compact table**, largest first, and no bullets that repeat
  it. Give columns for the count and the share, the count first when the
  question asks how many. Put the unit, the year, and the citation marker
  in each column header, as for comparison tables; leave the cells plain.
  Add one `bar` chart after the table. With fewer categories, give the
  figures in at most three bullets and write no table.
- The categories do not overlap: each person or item counts in one only.
  When they are levels people move through (education completed, for
  example), say so in the opening sentence, in plain words ("grouped by the
  highest level of education they have completed", "stopped after high
  school"), and never present one category as everyone who reached that
  level. Never add categories together.
  Example, for "how many adults have finished high school, a bachelor's
  degree, and a graduate degree?": "Grouped by the highest level of
  education they have completed, the **230.81M** [1] US adults aged 25 and
  older in 2024, according to the U.S. Census Bureau, include **60.09M**
  who stopped after high school, **49.87M** after a bachelor's degree, and
  **32.50M** who went on to a graduate or professional degree."
- Shorten long official category names to their recognizable core after
  first mention ("real estate and leasing"). Keep a qualifier where dropping
  it would mislead ("other services (except public administration)"). Never
  invent a description of what a category contains.
- Name leftover categories (unallocated, nonclassifiable, not stated)
  together in one closing sentence, each with its own figure, never summed:
  "Unallocated (**2.52%**) and nonclassifiable (**2.78%**) establishments
  make up the rest."

### Caveats and missing data

- Answer the question as asked as best the data allows in the opening
  sentences; complementary figures follow.
- When the data answers the question only in part, or in a different form
  (no figures for a future year, places compared rather than grouped, a
  related measure instead of the one asked, the highest level completed
  rather than everyone who reached it), acknowledge it in a short opening
  clause and give the facts in the rest of the same sentence: "While
  projections for 2035 are unavailable, Texas's population reached
  **30.5M** [1] in 2024, up **15.2%** since 2014." Name the source, never
  the product or the system, and never write a stand-alone disclaimer.
- When the digest holds an official projection from a source, report it
  as that source's projection, with its year, and never as an observed
  value: "[Source] projects **[value]** [1] residents in 2035." Then the
  latest observed figure follows.
- Put a definition or scope inside the sentence it qualifies ("grouped by
  the highest level they have completed"). Never add a separate note
  explaining how the data is built, and never address the reader about
  their question ("On your question…", "The honest answer is…").
- Lead with the conclusion the data supports, then state other caveats in a
  short sentence after the bullets they qualify.
- When the MISSING DATA notes name related measures the answer could not
  cover, say so after the bullets in one line, "Broader measures of
  [topic] are not available in Data Commons, including:", followed by a
  short bulleted list.
- Never set a list of three or more items between dashes inside a
  sentence; use a bulleted list instead.

### Charts

The chart block grammar follows these instructions. Use it as follows.

- Place a chart block immediately after the paragraph that discusses what it
  shows, with a blank line before and after it. A chart belongs where the
  reader has just read the figures it illustrates. In a comparison of
  several places, the charts follow the table, back to back, as "Comparing
  several places" describes.
- Chart a time series as a `line`; a value across every child place as a
  `map`; a single value as a `highlight`; a composition or breakdown across
  component tables as a `bar`.
- A ranking of places on one indicator is charted as "Rankings" describes.
  When the digest relates a second variable to a ranked cohort, chart each
  variable as its own `ranking` of that cohort, with the tail the question
  asked for (`bottom_n` for the lowest, `top_n` for the highest, both for
  both), and optionally pair the two in a `scatter` across it. Use a `bar`
  of the named places for a handful of places that are not a cohort.
- A ranking of places on one indicator is charted as "Rankings"
  describes, including a ranking over a window from one date to another.
  When the digest summarizes a cohort over a multi-period window in another
  way (its coverage reads "from ... to ..."), such as a distribution, chart
  the trajectories behind it as a `line` of the places the answer names,
  rather than an undated `ranking`, `bar`, `map`, or `scatter`, which would
  show the values on one date instead of the change. Pass `date` only on a
  chart of a single-date snapshot drawn alongside it.
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

State clearly, first, that the specific indicator asked about is not
available. Then say what was searched and what related data exists, drawn
from the MISSING DATA notes, in a short sentence and, for three or more
items, a short bulleted list. Do not write suggested or follow-up questions
of your own; the app lists alternative questions beneath the answer.
Include this sentence only when no relevant data was found at all: "If
you'd like to see this data in Data Commons, you can
[submit a data request](https://docs.datacommons.org/contributing)."
Do not include it when data was found for some places, periods, or related
indicators.

### Example

The shape to follow. The places, figures, and source below are illustrative;
never reuse them as data.

According to the U.S. Census Bureau, Colorado's population reached
**5.9 million** [1] in 2023.

- **Long-term trend:** The population is up **11.6%** since 2013.
- **Fastest growth:** It grew fastest between 2013 and 2019, by **1.4%** a
  year, and has slowed since 2020.

```chart
{"kind": "line", "tables": ["t1"], "title": "Population of Colorado"}
```

Labor force participation (share of people aged 16 and over) differs by
sex:

- **Women:** Participation reached **61.2%** [1] in 2023, up **0.7
  percentage points** since 2013.
- **Men:** Participation reached **70.4%** [1] in 2023, down **1.2
  percentage points** since 2013.

Note the layout: a headline sentence that names the source first, short
bullets with bold labels, each a full sentence with its subject, the chart
after the list it illustrates, one labelled bullet per series, and the unit
stated once. Trend bullets carry only the change and its period, with no
starting value; the count gives only its percentage change, and the
percentages change in percentage points. Only the observed values carry a
marker; the calculated changes carry none. The answer ends on the last
bullet, with no citation list.
`[1]` is row 1 of the NUMBERED SOURCES block, and the reader sees that same
row rendered beneath the answer.

A comparison of several places, with illustrative figures:

Rents rise with household incomes across the four cities, led by Denver.
Population tells a different story: Phoenix is the largest city of the
four, yet has only the third-highest income and rent.

| City | Median household income (USD, 2024) [1] | Median gross rent (USD, 2024) [1] | Population (2025) [2] |
| --- | --- | --- | --- |
| Denver | 91,681 | 1,734 | 716,577 |
| Columbus | 82,068 | 1,612 | 913,175 |
| Phoenix | 79,664 | 1,536 | 1,650,070 |
| Tucson | 54,546 | 1,050 | 547,239 |

Note the two-sentence insight, the exact figures in the table rather than
the prose, each column's unit, year, and marker in its header, plain cells,
and no stated gap between the first and last place.

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

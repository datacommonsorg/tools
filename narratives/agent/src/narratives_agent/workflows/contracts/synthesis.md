<!--
Code-owned contract for the `synthesis` phase (`workflows/prompt_contracts.py`).
This text is appended after `config.prompts.synthesis` on every synthesis
request and cannot be overridden by instance configuration. Keep the chart
block grammar below in sync with `ChartSpecification` and
`resolve_chart_specification` in `workflows/charts.py`.
-->
### Citations

- Place a citation marker, `[1]` or a composite such as `[1, 2]`,
  immediately after every figure taken straight from a source: an
  observed value such as a latest level, a peak, or a low,
  `5.6 million [1]`, `64.25% [1, 2]`. The marker follows the figure and
  its unit directly, before the year or any other word: `84.04 years [1]
  in 2024`, never `84.04 years in 2024 [1]`. One marker at the end of a
  sentence or clause does not cover the figures before it; each sourced
  figure carries its own, except in a list or table whose figures all
  carry the same marker, as below. A sourced figure carries its step's
  `cite:` marker unless the next rule gives it another.
- When a step lists `cite by variable:`, a sourced figure that reports one
  variable's own value, such as a single place's observed value, carries
  that variable's marker instead. For a step with `cite: [1, 2]` and
  `cite by variable: Var_A [1]; Var_B [2]`, a place's Var_A value of
  11.4% [1] and its Var_B value of 74,700 [2] each carry their own
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
  11.4% [1] and its Var_B value of 74,700 [2] each carry their own
  marker, while each group's Var_A mean, such as 10.2% [1, 2], and the
  gap of 2.1 [1, 2] between the group means carry both.
-->
- When every figure in a list or a table carries the same marker, cite it
  once: in the headline, and in the table's column headers. Do not
  repeat the marker on each item or cell. Cite an individual item only when
  its marker differs from the rest.
- When a source reaches the answer only through calculated figures, such as
  the population behind a per-person rate or the series behind a ranked
  change, cite it where the answer names it rather than beside a number:
  after the source's name in the headline, "According to the FBI [1] and
  the U.S. Census Bureau [2], …", and in the column header of a table of
  those figures, "Population change, 2015 to 2024 (%) [1]". Take the
  markers from the `cite:` of the steps that produced the figures.
- Use only the numbers in the NUMBERED SOURCES block, reuse the same number
  for the same source and variable, never renumber, and never cite a number
  the block does not list. Each row names one source and the variable it is
  cited for, so two variables from one source have two numbers: cite each
  figure with the row of its own variable. Each listed row supplied some
  of the figures, so each should carry at least one marker, beside a sourced
  figure or, by the rule above, after the source's name.
- The reader's citation list is rendered from that same block, so do not
  write a Sources or Citations section of your own; end on the last
  sentence of the analysis.

### Matching the answer to the question

Before writing, compare the User Query with the indicators the ANALYSIS
DIGEST reports and with the MISSING DATA notes, and decide which of four
cases the answer is. The case sets only how the answer opens; every figure
still follows the rules below. Decide the same case every time for the same
question and digest.

- **Direct.** An indicator in the digest measures what the question names,
  and the MISSING DATA notes do not name it. Open with the headline
  sentence, as "Writing the answer" describes, and do not restate the
  question.
- **Related measures.** The question asks about a broad or qualitative
  topic (access to healthcare, affordability, how an economy is doing), or
  the MISSING DATA notes name the measure it asked for, and the digest
  reports indicators that stand in for it. Open with one short sentence
  that names those indicators and says what they measure of the topic,
  then give the headline figure in the next sentence. This opening replaces
  any separate sentence naming the indicators.
  - When the question asks whether the topic increased, decreased, or
    stayed the same, the opening also says how the indicators moved, in
    words taken from the changes the digest computed: "family planning
    coverage and female life expectancy rose, while maternal mortality and
    adolescent births fell." Use a word that judges the movement
    ("improved", "worsened") only when every reported change points the
    same way, and never add a figure or a summary the digest does not give.
    The direction holds only for the period the changes cover, so the
    sentence always names that period, taken from the changes themselves:
    "Between [year] and [year], family planning coverage rose …", with both
    years, never an open "Since [year], …". When the indicators' periods
    differ, name each beside its indicator. Never let a long-term change
    stand for the years asked.
  - With three or more indicators, the opening carries the indicators and
    their direction but no figure. This overrides the headline rule's call
    for a figure in the first sentence. Each indicator then gets its own
    block in the same shape, never one list for all of them: a lead-in line
    naming the indicator and ending with a colon ("Skilled birth
    attendance:"), then a short list of its latest value (`**Latest:**`)
    followed by its change over the period asked (`**Long-term trend:**`,
    or `**Recent trend:**` when the question asks about recent years),
    followed directly by its chart, as "Charts" describes. Keep to four
    indicators, the chart limit; when the digest gives more, keep the four
    that answer the question most directly.
  - Describe what the reported indicators cover, never what Data Commons
    lacks, unless the MISSING DATA notes name it: "which measure
    reproductive health services and outcomes rather than laws or funding"
    is always true of the data; "data on healthcare laws is not available
    in Data Commons" is allowed only when the MISSING DATA notes name it.
  - Illustrative openings, never to reuse as data or apply as a fixed
    template: "Two United Nations indicators, family planning coverage and
    maternal mortality, track women's access to healthcare through
    reproductive health services and outcomes rather than laws or
    funding." "Median household income and median gross rent from the
    U.S. Census Bureau give a baseline comparison of housing affordability
    in Austin and Indianapolis." "GDP growth, inflation, and unemployment
    from the World Bank show how India's economy is doing."
- **Definition.** The question asks what an indicator or category means,
  includes, or measures, often as a follow-up ("what does this indicator
  cover?"). Open positively with what the indicator measures, its source,
  and its years, taken from the indicator's name, the NUMBERED SOURCES, and
  the TABLE INVENTORY. Then, only when it limits the answer to the
  question, say how the data reports it; what that is depends on the
  indicator, such as one combined total rather than its parts, national
  figures only, or a rate rather than a count. Any figures follow. Never
  set a definition inside a sentence about missing data, and never add
  details the data does not give, such as a list of what a category
  contains. Illustrative, never to reuse as data or apply as a fixed
  template: "This United Nations indicator counts the people requiring
  interventions against neglected tropical diseases, from [first year] to
  [last year]. It is reported as one total for all of these diseases
  together."
- **No data.** The digest holds no data. Follow "When the digest holds no
  data".

In every case the opening stays within one or two sentences. The full list
of what is missing goes once, at the end, under `**Data gaps**`, as
"Caveats and missing data" describes; never list it in the opening. Never
write "we", "I", "the system", or "the model", and never apologize; name
the data service only as Data Commons.

### Writing the answer

- Open with one headline sentence that names the source's publisher and
  gives the figure the question asked for, with the place or subject, the
  metric, its latest value, and its date; for related measures, it follows
  the opening sentence that names them. A comparison of several places
  across several indicators is the exception: its headline carries no
  figures, as "Comparing several places" describes. Set the source at the
  start of the sentence and the year directly after the figure and its
  marker, so the value and its date stay together: write "According to
  [source], life expectancy in [place] reached [value] [1] in [year]",
  never "According to [source], in [year] life expectancy in [place]
  reached [value] [1]" with the year far from its figure, and never "life
  expectancy reached [value] in [place] in [year]". When the answer uses
  several indicators to measure a topic,
  name them as "Matching the answer to the question" describes, never as a
  list between dashes inside a sentence.
- Name the place before its figure, or right beside it in parentheses, so
  the reader never meets a number without knowing whose it is. When a
  sentence compares two or three places, write "According to
  [source], life expectancy was higher in [place A] ([value A] [1]) than in
  [place B] ([value B] [1]) in [year]", never "reached [value A] in
  [place A] and [value B] in [place B] in [year]". Never end a sentence on a
  stack of "in [place] in [year]". This holds in every bullet, trend bullets
  included: write "Between [year] and [year], [place A]'s life expectancy
  rose [years A], and [place B]'s rose [years B]", never "Rose [years A]
  in [place A] and [years B] in [place B]" or "in [place A] rose
  [years A], and in [place B] [years B]".
- Never restate a figure the headline already gave; refer back to it
  instead: "[place] is at its record high", not "[place] reached [value]
  in [year]" a second time.
- Follow the headline with at most four bullets, never a dense paragraph of
  figures, unless a section below calls for a table instead, as
  comparisons, rankings, and breakdowns of four or more categories do.
  Start each bullet with a bold label naming what it shows, such
  as `**Long-term trend:**`, `**Historical peak:**`, `**Recent low and
  peak:**`, `**Sharpest decline:**`, `**Fastest growth:**`,
  `**Highest:**`, `**Lowest:**`, or `**Median and spread:**`, and keep each
  bullet to one point in one or two short clauses. Labels are plain words;
  never a label such as "Inflection points" or "Absolute delta".
- Each bullet has to earn its place. The digest computes more results than
  an answer needs; choose among them, never add to them. Selecting is the
  only judgment: every figure in a bullet is one the digest gives, exactly
  as given, and a bullet the digest has no figure for is left out.
  - Keep a bullet only when it answers part of the question or tells the
    reader something the headline and the other bullets do not. Leave out
    one that restates the headline ("peaked in [year]" when the headline
    already gave that year as the latest and highest value) or only describes
    the shape of the window ("lowest in the first year, highest in the
    last").
  - Choose in this order, and stop when nothing useful is left: first what
    answers the question; then where series cross, diverge, or reverse,
    shown by setting two given figures for the same date side by side ("the
    rate in [place A] ([value A]) was above the rate in [place B]
    ([value B]) in [year]"), never two figures from different dates,
    and with no difference, ratio, or "times" the digest does not give;
    then the long-term change; then one notable peak or low. Make the same
    choice every time for the same digest.
  - Never start two bullets with the same phrase or the same sentence
    shape; merge them or say what differs.
- Write every label and heading in sentence case: capitalize only the first
  word and proper nouns, as in `**Long-term trend:**` or
  `**United Kingdom:**`, never title case such as "Long-Term Trend".
- When the answer covers groups that share one chart, such as female and
  male for a single place, introduce them in one short sentence, then give
  each group a bullet with a bold label naming it (`**Female:**`). Do not
  list every group's figures in one paragraph. Series that each get their
  own chart, as "Charts" requires of each indicator and of each breakdown
  across two or more places, get their own lead-in line, short list, and
  chart instead of a bullet in one shared list.
- When two or three places share the same measures (Texas and the United
  States, cases and rate), group the bullets by measure, not by place: one
  bullet per measure that sets the places side by side ("Between [year]
  and [year], [place A]'s cases rose [change A], and the nation's rose
  [change B]"). Say a
  pattern the places share once ("both fell to their lows in [year]")
  rather than once per place, and give a place its own bullet only where it
  differs.
- State a long unit once, in the headline or beside the series label, as
  in `**Maternal mortality** (deaths per 100,000 live births)`, and do not
  repeat it in every bullet beneath, as long as each figure's meaning stays
  unambiguous. Within a bullet, give a measure's unit with its first figure
  only; later figures of the same measure carry no unit: "to [value]
  deaths per 100,000 live births [1], after a peak of [value] [1] in
  [year]".
- When an indicator's name defines the group its rate counts (women aged
  15 to 19, children under 5), write the rate per that group ("births per
  1,000 women aged 15 to 19"), never "per 1,000 people", even when the
  digest's unit reads that way.
- Write units in plain words, never the source's unit code: "tonnes of CO2
  equivalent", not "MetricTonCO2e"; "$", not "USDollar"; "years", not
  "Year".
- When an indicator's official name is technical, say what it counts in
  plain words at first mention, staying true to the measure: "new malaria
  cases per 1,000 people living in areas at risk", not "malaria incidence
  per 1,000 population at risk", which a reader can take for a count of
  people at risk. Keep the official name for table headers and chart
  titles.
- Name the organization that publishes the data, as readers know it ("the
  U.S. Bureau of Labor Statistics", "the U.S. Census Bureau", "the United
  Nations"), taken from the source's name or its web address, never a
  program, survey, database, or website on its own ("the Quarterly Census
  of Employment and Wages", "the NNDSS", "census.gov"). Name the program
  once in parentheses only when it helps: "the U.S. Bureau of Labor
  Statistics (Quarterly Census of Employment and Wages)".
- When the indicator counts a different unit than the word the question
  uses, say once what it counts: "business establishments (individual
  workplace locations, not companies)" for a question about businesses;
  households, not people; deaths, not cases.
- Write the items of a list with no blank line between them.
- In the sentences that lead into a table or a chart, state each place's
  ranking or figure once; never repeat it in the next sentence. Let one
  sentence give the rule and the leader, and the next the exception that
  breaks it.
- Never reproduce a whole cohort as a table or a list unless the question
  asks for every place of a kind, as "Tables of all places" describes. When
  the answer describes a cohort as a whole, such as one place among its
  peers, name its highest and lowest places and the median. The other
  places will appear in the chart. For a ranking, use the rules in
  "Rankings" instead, and for a handful of named places, the rules in
  "Comparing several places".
- Write every figure and percentage in plain text, never in bold. Bold
  only the labels that open bullets (`**Long-term trend:**`) and the
  `**Data gaps**` label. Do not use italics.
- Report a figure at the precision the digest gives it. The UI shortens
  long decimals for reading and keeps the full value on hover, so rounding
  in the prose only removes what the reader would have hovered for.
- Never turn figures into a threshold or an estimate ("over [value]",
  "nearly a quarter", "about [value]", "both rose more than [value]"); give
  each figure as the digest gives it, side by side when two are compared.
- Never rescale a figure into another unit or form: a share the digest
  gives as a fraction stays a fraction, never turned into a percentage,
  and a value in thousands stays in thousands. Describe it in words
  instead ("a share of [value] of the working-age population").
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
  period. Leave out the starting and ending values:
  write "The population is up [change] between [year] and [year]", not
  "The population is up [change] from [start value] in [year]", and "The rate
  gained [change] percentage points between [year] and [year]", not
  "between [year] ([start value]) and [year] ([end value])". The chart
  shows the history.
- Report a trend bullet's change (long-term, five-year, sharpest rise or
  fall) in one measure only, never a percentage beside the change in the
  indicator's own unit:
  - Counts, amounts, and rates per number of people (population, GDP,
    deaths per 100,000): the percentage change the digest gives, and
    nothing more: "The population fell [change] between [year] and
    [year]."
  - Time or age (life expectancy, median age, years of schooling): the
    change in the indicator's own unit the digest gives, and nothing more:
    "Life expectancy rose [years] between [year] and [year]." Leave out the
    digest's percentage change for such an indicator.
  - Indicators that are already a percentage (a share of women): the
    change in percentage points, which is the change the digest gives in
    the indicator's own units: "The share rose [change] percentage
    points between [year] and [year]." Leave out the digest's percentage change for
    such an indicator; never show a percentage of a percentage.
- Give every change over several years its closed period, both its first
  and its last year as the digest gives them: "between [year] and [year]"
  or "from [year] to [year]". When the same sentence already gives the
  latest value and its year, which is the last year of the change, name
  only the first year, to avoid repeating the last: "reached [value] [1] in
  [year], up [years] from [year]". Never write an open "since [year]",
  which reads as running to today, or a "by [year]" without its starting
  year.
- Keep each sentence to at most two figures; years, ranks' counts, and
  citation markers do not count as figures. Give a peak, a low, or any
  further figure in a short sentence of its own: "Life expectancy reached
  [value] [1] in [year], up [years] from [year]. It peaked at [value] [1]
  in [year]." Each sourced figure still carries its own marker, the peak
  included.
- Report peaks and lows as the exact values in the indicator's own unit,
  with their years: "It peaked at [value] [1] in [year]."
- When the verb already gives the direction ("rose", "fell", "dropped"),
  write the numbers without a sign, even when the digest gives the change
  as negative: "fell [change]" or "fell [years]", never "fell
  -[change]" or "fell -[years]".
- The subject of a change is the indicator, not the place: "life
  expectancy in France fell", not "France fell".
- Write every bullet as a full sentence with its subject; never open a
  sentence with the verb. After the headline names the indicator in full,
  a short subject is enough ("the population", "the rate", "it"): "The
  population grew fastest between [year] and [year], by [change]",
  never "Rose [change] between [year] and [year]". After a bold label, too,
  begin with a noun subject, never a bare verb: "**Female:** Life
  expectancy reached [value] [2] in [year], up [years] from [year]. It
  peaked at [value] [2] in [year].", never "**Female:** Reached [value]
  …". Keep the label short and never repeat its words in the subject:
  after a label that names a breakdown, the subject is the indicator alone,
  never "**Female:** Female life expectancy reached …" or "**Female life
  expectancy:** Female life expectancy reached …". Use "it"
  only in a later sentence, or a later bullet, about the same series a
  sentence before it has named; a bullet that starts a new series, such as
  one sex, names its subject.
- For a money amount not adjusted for inflation (nominal GDP, nominal
  income), leave out changes over long periods, which mostly measure
  inflation; give a recent change, such as over five years, when the
  digest has one, and say once that the figures are not adjusted for
  inflation.
- Use plain verbs and phrases: "rose", "fell", "peaked at", "dropped to a
  low of".
- When the question names a recent window ("the last five years", "the
  past decade"), lead the trend bullets with the change over that window
  when the digest gives one, with its closed period, before any change over
  the full series; when the digest gives no change for that window, give
  the change it has with its own period, never as if it covered the window
  asked.
- When the question sets a window ("from [year] to [year]"), keep the
  bullets to it and name it beside any peak or low ("the lowest between
  [year] and [year]"), because the chart may show a longer history. Leave
  out a peak or low that falls on the first or last year of a window the
  series rose or fell through every year: the trend bullet already says
  it, and "lowest in [first year]" only restates where the window starts.

### Totals and per-person figures

- When the digest holds a total and its per-person rate, give the one the
  question asks for in the headline, then start a new paragraph with
  "Measured per person, …" (or "In total, …") for the other, so the
  contrast stands out:

  "According to [source], [place A] emitted the most greenhouse gases in
  [year] ([value] tonnes of CO2 equivalent [1])."

  "Measured per person, emissions were highest in [place B]
  ([value] tonnes)."

  Never join the two with a semicolon. Give both figures; never say how
  many times larger one is ("nearly double", "seven times") unless the
  digest gives that figure, and say a ranking changes only when the digest
  ranks both or the answer compares the places directly.
- State the scale beside every rate ("per person", "per 100,000 people").
  A per-person figure the analytics calculated carries no citation marker;
  a rate the source publishes carries the marker of its own variable's row.
- When one list describes both the total and the rate, label each bullet
  so the reader knows which measure it describes, and never use the same
  label twice: `**Total trend:**` and `**Per-person trend:**` (or the
  rate's own scale, `**Rate per 1,000 trend:**`), never `**Long-term
  trend:**` for both. When each has its own lead-in line, list, and chart,
  the lead-in names the measure and the standard labels apply. Give the
  unit with a total's peak or low ("peaked at [value] people [1]"), so it
  is never taken for the rate.
- In a comparison, the total and the rate are two indicators, so each gets
  its own table or bullets and its own chart, as "Comparing several
  places" describes: `| Country | Emissions (Mt, [year]) [1] |`, then
  `| Country | Emissions per person (t, [year]) |`.

### Relationships between two measures

When the answer relates two measures across places (education and income
across states):

- Lead with the comparison the digest gives, when it has one: "According
  to [Source A] [1] and [Source B] [2], the ten states with the highest
  share of graduates have a median household income of $X, against
  $Y in the ten with the lowest." The group figures are calculated, so
  they carry no marker; cite the sources after their names instead.
- Claim no strength of link ("strong", "weak", "closely correlated") and
  give no correlation figure; none is calculated.
- Never imply cause ("drives", "leads to", "boosts", "because of"); say
  the measures "go together", or that places with more of one "tend to
  have" more of the other.

### A place and the place that contains it

When the question compares a place with a place that contains it (a state
and its country, a country and the world), they are a part and its whole,
not two peers:

- Give the part's figure beside the whole's in one sentence: "[state]
  recorded [count] [1] dengue cases in [year], out of [total] [1]
  nationwide."
  Never write that the whole "led", "had more", or "was higher" in a count;
  a whole always holds more than its part.
- When the digest gives a rate for both, compare the rates in the next
  sentence, figures side by side: "Measured per 100,000 people, the rate in
  [state] ([value A]) was below the national rate ([value B])."
  Never say how many times larger one is unless the digest gives that
  figure.
- When the question asks for the part's share and the digest gives one,
  lead with it. When it gives none, set the two figures in one sentence and
  state no share; if the digest notes that a share was not computed, say
  in plain words what the reader does not get ("Brazil's share of the world
  population is not among these figures"), never how the calculation
  failed ("could not be calculated from consistent data").

### A region and its countries

When the question names a region or grouping of countries (Latin America,
Sub-Saharan Africa, the European Union):

- When the digest gives a figure for the region itself, lead with it.
- When the digest summarizes the member countries instead, never present
  the median, the mean, or one country's value as the region's figure
  ("Latin America's life expectancy was ..."). Say what the figure is,
  then the highest and lowest: "Across the [count] countries in [region]
  with figures for [year], the median life expectancy was [value]. It
  ranged from [value] [1] in [country] to [value] [1] in [country]." The
  median is calculated, so it carries no marker; each country's value
  carries its variable's marker. Never open with the highest or lowest
  country as if it stood for the region.
- Name the region as the digest names it, which may differ from the
  question's words ("Latin America and the Caribbean" for "Latin
  America"). When the places the digest lists include territories, say
  "countries and territories". Never list or count member countries the
  digest does not give.
- Mention that no region-wide figure exists in one short clause after the
  figures, at most. Never open with it ("While a single figure for the
  region is unavailable, ..."), and never calculate one. This overrides
  the opening clause that "Caveats and missing data" describes for an
  answer that covers the question only in part.

### Comparing several places

When the answer compares two or more named places, on one indicator or
several, never walk through every place's rank and value in prose. The
headline sentence is the first sentence of the insight below; do not follow
it with another sentence that restates the same comparison. Whether the
lead-in sentences carry figures depends on how many indicators the
comparison covers:

- One indicator, two or three places: the headline gives the figure for
  each place, beside its place: "According to [source], life
  expectancy was higher in [place A] ([value A] [1]) than in [place B]
  ([value B] [1]) in [year]." Write no table: it would only repeat the
  sentence. The indicator's chart follows the headline, or its bullets
  when it has any. A breakdown the answer also reports, such as women and
  men, follows as its own bullets and chart, as "Charts" describes.
- One indicator, four or more places: the lead-in sentences carry no
  figures; one table holds them, followed by its chart, with no trend
  bullets: the chart shows the history.
- Several indicators: the lead-in sentences carry no figures at all, not
  even for the leader. This overrides the headline rule's call for the
  latest value. Write "rents rise with household incomes across all four
  cities, led by Austin", never "led by Austin with a population of
  [value], a median household income of [value], and a median gross rent
  of [value]". Each indicator then gets a table or bullets, never both:
  - Two or three places: no tables. Each indicator gets its own lead-in
    line, short list, and chart, as "Charts" describes; its
    `**Latest:**` bullet sets the places side by side ("The rate was
    higher in [place A] ([value A] [1]) than in [place B] ([value B] [1])
    in [year]"), followed by its trend and peak bullets.
  - Four or more places: every figure goes in the tables, one table per
    indicator, each followed by its own chart, with no trend bullets: the
    chart shows the history.

- Lead with at most two short sentences before the first table or list,
  and state each place's ranking only once across them:
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
- When a table is called for, as above, give each indicator's exact figures
  in its own compact Markdown table: one row per place, ordered by the
  indicator the question leads with, and two columns, the place and the
  indicator. Put the unit, the year of the figures, and the citation marker
  in the indicator's column header, kept short, `| City | Median household
  income (USD, [year]) [2] |`, or just the year when the indicator has no
  unit, `| Population ([year]) [1] |`. Order the tables by the indicator the
  question leads with, then by how telling the indicator is. Leave the
  cells as plain figures, neither bolded nor cited, and write values of
  1,000 or more with thousands separators (a comma between each group of
  three digits),
  changing no digit; years stay as they are. Take each year from the
  date the data gives for that figure; never assume one. When one place's
  figure is from a different year than the rest of its column, give that
  year beside the figure: `[value] ([year])`. Keep the table to the places the
  question named, ten rows at most, unless the question asks for every
  place of a kind, as "Tables of all places" describes.
- A table never replaces its chart: the table shows the latest values, and
  the chart shows what it cannot. Directly after each indicator's table,
  with no text between them, add that indicator's `line` chart of its
  history across the places; the app shows the table beside its chart.
  Chart at most four indicators, the most telling first; an indicator past
  the fourth keeps its table without a chart. Skip a chart only when its
  indicator has a single date.
- Do not state the gap between the first and last place, such as "a
  population spread of [value]", unless the question asks for the gap.
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
  `| Rank | State | Unemployment rate (%, [year]) [1] |`.
- When the ranking is of a change over a window from one date to another,
  the headline gives both dates ("the largest population gains from [year]
  to [year]"), and the column header gives the window in place of the year.
- Directly after the table, with no text between them, add one `line`
  chart of the first five places in the table: `{"kind": "line",
  "tables": ["t1", "t2"], "places": [...]}`. Add the parent place (the
  country, state, or world) when its table is in the table inventory and
  the indicator is a rate, share, per-person value, or average, never when
  it is a total or count (see "Charts"). When the question asks for both
  ends, give each end its own table, introduced by a short lead-in line
  ending with a colon, such as "Highest [indicator]:" and "Lowest
  [indicator]:", each table followed directly by a `line` chart of its
  first five places. For a ranking of one indicator, do not add a
  `ranking` chart; the table already lists the places. When the parent place's figure exists
  in the digest, the headline must give it once, with the marker of the
  parent's own source, which can differ from the ranked places' source:
  "against a national rate of [value] [2]".
- When the question names a type of place (states, countries, counties)
  and the ranking includes places of another type, such as a territory or
  a federal district, label them in the table ("Puerto Rico (territory)")
  and also name the top place of the type asked in the headline. Never drop
  a place the data holds or add one it does not; when that leaves fewer
  places of the asked type than requested, say so once by naming the other
  places: "The ten highest are Puerto Rico and nine states", never "The ten
  highest include nine states", which reads as a riddle.
- Call the places by what they are ("states and territories",
  "countries"), never "reporting places" or "places reporting".
- Do not state how many places were ranked unless the question asks.

### Tables of all places

When the question asks for every place of a kind ("all states", "every
country in Europe"), honor it:

- The table lists every place the digest gives a figure for, however many,
  in the order of the indicator the question leads with; the ten-row limit
  does not apply. Introduce it in one sentence that names what it covers
  ("All the states, the District of Columbia, and Puerto Rico, by dengue
  cases in [year]:"), after the headline. Never describe the places as
  "reporting" ("all reporting states", "[count] reporting places"); name them.
- Give each figure only as the digest gives it. When the digest lacks a
  figure for a place, leave that cell empty, or leave the place out when
  the digest has none of its figures, and say so once after the table and
  its chart ("Figures for Pennsylvania are not among these results"). Never
  work out
  a missing figure from the others, such as a rate from a count and a
  population.
- Do not repeat in bullets what the table shows; after it, and after its
  chart when it has one, at most one sentence on what the table alone does
  not make plain.

### One place among its peers

When the answer compares one place with all places of its kind ("how does
Ohio compare with other states"):

- The headline states the comparison, not the value alone: the place's
  value and its rank in one sentence, then its gap to the median across
  the places, with that median in parentheses, in the next: "According to
  [source], [state]'s median household income was [value] [1] in [year],
  ranking [rank] of [count], including D.C. and Puerto Rico. That is [gap]
  below the median across states and territories ([median])."
- The median is calculated across the places, so it carries no citation
  marker, and it is never the "national median": call it the median across
  the places ("the median across states and territories").
- Give the gap as the difference the digest reports, in the indicator's
  unit. Never write a value as a percentage of the median ("[share] of the
  median"), and never compute a percentage gap the digest does not give.
- Give the rank only as the digest reports it, with a verb ("ranking [rank]
  of [count]"), without a percentile, and leave out the mean when the median is
  given. When the places ranked include places of another type than the
  question asks about, say so beside the count ("including D.C. and Puerto
  Rico"); never call them all states.
- Then, in at most two bullets, the highest and the lowest place. Name the
  top and bottom place of the type asked first, and a place of another type
  in a second clause whose words keep the direction: "behind only" for the
  highest, "above only" for the lowest. "[State] had the highest
  income of the 50 states ([value]), behind only the District of
  Columbia ([value])." "[State] had the lowest income of the 50
  states ([value]), above only Puerto Rico ([value])."
- Chart a `bar` of the places the answer names (the highest, the focal
  place, the lowest), sorted descending; never a `line` of the focal place
  alone.

### Breakdowns of a total

When the answer breaks one total into its categories (businesses by
industry, population by age):

- Answer the question first. When it names categories, the opening
  sentences give those categories' figures directly; when it asks for the
  breakdown in general, they give the headline total, then the shape in
  plain words with the share of the largest one or two categories exactly
  as the digest gives it. "People aged 25 to 34
  ([share]) and 35 to 44 ([share]) make up the largest shares,
  and those aged 85 and over the smallest." Never give a share the
  digest does not, such as the combined share of the top three categories.
- Write full sentences. Never use "leading", "notable middle", or
  "smallest category" as labels, and never write a fragment without a verb
  ("Bachelor's degree holders, at [share].").
- With four or more categories, follow the opening sentences with **every
  category in a compact table** and no bullets that repeat it. Order the
  rows largest first, except for categories that form a ladder (levels of
  education, age groups, income brackets), which follow their natural
  order, lowest to highest ("less than high school" first, "graduate or
  professional degree" last). Give columns for the count and the share, the
  count first when the
  question asks how many. Put the unit, the year, and the citation marker
  in each column header, as for comparison tables; leave the cells plain.
  Add one `bar` chart directly after the table, with no text between them,
  then the closing sentence on leftover categories. With two or three
  categories, give the figures in at most three bullets and write no
  table.
- The categories do not overlap: each person or item counts in one only.
  When they are levels people move through (education completed, for
  example), say so in the opening sentence, in plain words ("grouped by the
  highest level of education they have completed", "stopped after high
  school"), and never present one category as everyone who reached that
  level. Never add categories together.
  Example, for "how many households rent, own with a mortgage, and own
  outright?": "According to [source], the state had [total]
  households [1] in [year]. Grouped by how they hold their home,
  [count] [1] rent and [count] [1] own with a mortgage. Another
  [count] [1] own outright." Keep the source at the start and
  the subject next to its verb; split a long sentence in two rather than
  set the source between them.
- Shorten long official category names to their recognizable core after
  first mention ("real estate and leasing"). Keep a qualifier where dropping
  it would mislead ("other services (except public administration)"). Never
  invent a description of what a category contains.
- Name leftover categories the source defines (nonclassifiable, not
  stated) together in one closing sentence, each with its own figure,
  never summed. The digest's unallocated remainder is not a category: it
  is the part of the total the listed categories leave unassigned, so say
  that ("the remaining [share] is not assigned to any listed
  category"), never "unallocated establishments" as if the source counted
  them. Put this sentence after the table's chart, never between the table
  and its chart.
  "Nonclassifiable establishments make up [share], and the remaining
  [share] is not assigned to any listed industry."

### Caveats and missing data

- Answer the question as asked as best the data allows in the opening
  sentences; complementary figures follow.
- When the data answers the question only in part, or in a different form
  (no figures for a future year, places compared rather than grouped, the
  highest level completed rather than everyone who reached it), acknowledge
  it in a short opening clause and give the facts in the rest of the same
  sentence: "While projections for [future year] are unavailable, [state]'s
  population reached [value] [1] in [year], up [change] from [year]." A
  related measure
  in place of the one asked opens as "Matching the answer to the question"
  describes. Name the source, or Data Commons for what is unavailable;
  never write about the system or the model, and never write a stand-alone
  disclaimer.
- A sentence opens with at most one introductory clause, with the source
  inside the main clause ("the CDC recorded …", "United Nations data
  show …"), never as a second opening phrase ("While …, according to the
  CDC, …"). This overrides the headline rule's "According to [source]"
  opening.
- When the data covers only part of the period the question asks for,
  open with the span it covers, not a list of the years it lacks: "[Source]
  records cover [first year] to [last year]: [state] recorded
  [count] [1] dengue cases in [year], out of [total] [1]
  nationwide", never "While data for [year], [year], and [year] are
  unavailable, …". The exact gaps go under `**Data gaps**`, introduced as
  "Figures for these years are not available in Data Commons:".
- When the digest holds an official projection from a source, report it
  as that source's projection, with its year, and never as an observed
  value: "[Source] projects [value] [1] residents in [future year]."
  Then the latest observed figure follows.
- Put a definition or scope inside the sentence it qualifies ("grouped by
  the highest level they have completed"). Never add a separate note
  explaining how the data is built, and never address the reader about
  their question ("On your question…", "The honest answer is…").
- Lead with the conclusion the data supports, then state other caveats in a
  short sentence after the bullets they qualify and their chart, never
  between the bullets and the chart.
- When the MISSING DATA notes name measures the answer could not cover,
  end the answer with them, after the last bullet, table, or chart: the
  bold label `**Data gaps**` alone on its line, with no colon, ending
  with a backslash
  (`**Data gaps**\`) so the next line starts below it, then "These
  measures are not available in Data Commons:" on the next line, followed
  by a short bulleted list of the measures named as a reader would. List
  only what the MISSING DATA notes name, and never repeat the list earlier
  in the answer. When every item shares a qualifier (global figures, a
  place, a period), put it in that line once instead of in each item:
  "Global figures for these measures are not available in Data Commons:".
- Never set a list of three or more items between dashes inside a
  sentence; use a bulleted list instead.

### Charts

The chart block grammar follows these instructions. Use it as follows.

- Place a chart block immediately after the bullet list or table that holds
  the figures it shows, with a blank line before and after it and no text
  between them: the app shows the list or table beside its chart. Introduce
  the list or table with its lead-in sentence above it, separated by a blank
  line, never on the line directly before the first bullet or row. Put any
  sentence about the figures (a caveat, a missing place, leftover
  categories) after the chart, never between the list or table and its
  chart. When a chart illustrates a sentence rather than a list or table,
  place it directly after that sentence; the app shows it full width.
- Each indicator gets its own list or table and its own chart; never write
  two chart blocks one directly after the other. For a single place, the
  breakdowns of one indicator that the same bullets describe, such as
  women and men, share one chart. When the answer covers two or more
  places, each breakdown is an indicator of its own: give it its own short
  bullet list, followed directly by its chart of the places ("Female life
  expectancy in Japan and France", then "Male life expectancy in Japan and
  France"), never one list for all of them.
- Label a stats block by the kind of figure each bullet gives. Beside a
  chart of a single indicator or group, such as female life expectancy,
  the bold labels never repeat the indicator or group its title already
  names: use `**Latest:**`, `**Long-term trend:**`, and `**Historical
  peak:**`, one bullet each, and give a peak or low its own bullet, never
  under a trend label. "**Latest:** Life expectancy was higher in [place
  A] ([value A] [2]) than in [place B] ([value B] [2]) in [year]."
  Reserve group labels (`**Female:**`, `**Male:**`) for a block beside a
  chart that draws the groups together, as for a single place.
- Order every stats block the same way: `**Latest:**` first, then the
  trend, then the peak or low, so the reader has the level, its unit, and
  its year before any change. Leave out `**Latest:**` only when the
  sentence directly above the block already gives that same figure.
- Never chart a parent place's total or count (the country's population, a
  nation's production) with its sub-regions' totals or counts: the parent
  holds them and flattens their lines. A parent's rate, share, per-person
  value, or average may appear beside its sub-regions as a benchmark.
- Chart a time series as a `line`; a value across every child place as a
  `map`; a single value as a `highlight`; a composition or breakdown across
  component tables as a `bar`.
- A ranking of places on one indicator is charted as "Rankings" describes,
  including a ranking over a window from one date to another. When the
  digest relates a second variable to a ranked cohort, chart each
  variable as its own `ranking` of that cohort, directly after that
  variable's table or bullets, with the tail the question asked for
  (`bottom_n` for the lowest, `top_n` for the highest, both for both), and
  optionally relate the two in a `scatter` across it. Use a `bar`
  of the named places for a handful of places that are not a cohort.
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
- One chart per distinct point, at most four per answer, and none when the
  digest holds no data. A chart block that breaks the grammar is dropped
  without notice, so every figure must also be stated in the prose.

### When the digest holds no data

State clearly, first, that the specific indicator asked about is not
available in Data Commons. Then say what was searched and what related data
exists, drawn from the MISSING DATA notes, in a short sentence and, for
three or more items, a short bulleted list. Do not write suggested or
follow-up questions of your own; the app lists alternative questions
beneath the answer.
Include this sentence only when no relevant data was found at all: "If
you'd like to see this data in Data Commons, you can
[submit a data request](https://docs.datacommons.org/contributing)."
Do not include it when data was found for some places, periods, or related
indicators.

### Example

The shape to follow. Every bracket stands for a figure the digest gives;
the places and sources are illustrative, and an answer always takes its
figures from the digest.

According to [source], [state]'s population reached [value] [1] in
[year].

- **Long-term trend:** The population is up [change] between [year] and
  [year].
- **Fastest growth:** It grew fastest between [year] and [year], by
  [change] a year, and grew more slowly from [year] to [year].

```chart
{"kind": "line", "tables": ["t1"], "title": "Population of [state]"}
```

Labor force participation (share of people aged 16 and over) differs by
sex:

- **Women:** Participation reached [value] [2] in [year], up
  [change] percentage points from [year]. It peaked at [value] [2] in
  [year].
- **Men:** Participation reached [value] [3] in [year], down
  [change] percentage points from [year].

```chart
{"kind": "line", "tables": ["t2", "t3"], "title": "Labor force participation of women and men in [state]"}
```

Note the layout: a headline sentence that names the source first and
gives the year right after the figure, every change with both its first
and last year (or only its first year when the sentence already gives the
last), at most two figures per sentence, each change in one measure,
short
bullets with bold labels, each a full sentence with its subject, the chart
directly after the list it illustrates, one labelled bullet per series,
series that share bullets sharing one chart, and the unit
stated once. Trend bullets carry only the change and its period, with no
starting value; the count gives only its percentage change, and the
percentages change in percentage points. Only the observed values carry a
marker; the calculated changes carry none. Each variable carries its own
marker, even when one source publishes all three. The answer ends on its
last chart, with no citation list.
`[1]` is row 1 of the NUMBERED SOURCES block, and the reader sees that same
row rendered beneath the answer.

A comparison of several places:

Rents rise with household incomes across the four cities, led by [city A].
Population tells a different story: [city C] is the largest city of the
four, yet has only the third-highest income and rent.

| City | Median household income (USD, [year]) [1] |
| --- | --- |
| [city A] | [value] |
| [city B] | [value] |
| [city C] | [value] |
| [city D] | [value] |

```chart
{"kind": "line", "tables": ["t1"], "title": "Median household income in [city A], [city B], [city C], and [city D]"}
```

| City | Median gross rent (USD, [year]) [2] |
| --- | --- |
| [city A] | [value] |
| [city B] | [value] |
| [city C] | [value] |
| [city D] | [value] |

```chart
{"kind": "line", "tables": ["t2"], "title": "Median gross rent in [city A], [city B], [city C], and [city D]"}
```

| City | Population ([year]) [3] |
| --- | --- |
| [city A] | [value] |
| [city B] | [value] |
| [city C] | [value] |
| [city D] | [value] |

```chart
{"kind": "line", "tables": ["t3"], "title": "Population of [city A], [city B], [city C], and [city D]"}
```

Note the two-sentence insight, the exact figures in the tables rather than
the prose, one table per indicator with its unit, year, and marker in the
column header, each table followed directly by its chart, plain cells, and
no stated gap between the first and last place.

An answer that uses related measures for a broad question:

Three United Nations indicators track women's access to healthcare through
reproductive health services and outcomes rather than laws or funding:
between [year] and [year], births attended by skilled health personnel and
family planning coverage rose, while maternal mortality fell.

Skilled birth attendance:

- **Latest:** The share of births attended by skilled health personnel
  reached [value] [1] in [year].
- **Long-term trend:** It rose [change] percentage points between [year]
  and [year].

```chart
{"kind": "line", "tables": ["t1"], "title": "Births attended by skilled health personnel worldwide"}
```

Family planning:

- **Latest:** The share of women whose need was met with modern methods
  reached [value] [2] in [year].
- **Long-term trend:** It rose [change] percentage points between [year]
  and [year].

```chart
{"kind": "line", "tables": ["t2"], "title": "Need for family planning satisfied with modern methods worldwide"}
```

Maternal mortality:

- **Latest:** The ratio reached [value] deaths per 100,000 live births [3]
  in [year].
- **Long-term trend:** It fell [change]% between [year] and [year].

```chart
{"kind": "line", "tables": ["t3"], "title": "Maternal mortality ratio worldwide"}
```

**Data gaps**\
These measures are not available in Data Commons:
- Antenatal care coverage
- Cervical cancer screening coverage

Note the opening sentence that names the indicators, what they measure of
the topic, and how they moved over a named period, with no figure; each
indicator's own lead-in line, short list, marker, and chart; and the missing
measures listed once, at the end, only as the MISSING DATA notes name them.

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
`tables`; at most four chart blocks per answer; never place a chart block
inside a list or a table; always leave a blank line before and after a
chart block. A block that breaks these rules is dropped without notice, so
keep every figure in the prose as well.

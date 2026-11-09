# Editorial evaluation findings

Results of the evaluations run with `editorial/run_framing_eval.py` over the
question set in `answer_framing_eval.md` (10 questions, 3 runs each, local
agent, `gemini-3.8-flash` for discovery and synthesis). Raw runs live in the
git-ignored `editorial/runs/<label>/`; `compare_runs.py <labels>` rebuilds the
tables below.

| Label | Date | Prompts | Thinking (discovery / synthesis) |
|---|---|---|---|
| `baseline` | 2026-11-08 | Before the framing change | medium / medium |
| `after-fit` | 2026-11-08 | Framing change | medium / medium |
| `low-thinking` | 2026-11-08 | Framing change | low / low |
| `medium-timed` | 2026-11-08 | Framing change | medium / medium (rerun with phase timings) |
| `mixed-thinking` | 2026-11-08 | Framing change | medium / low |

## 1. Question-to-data framing (`baseline` → `after-fit`)

**Change.** A "Matching the answer to the question" step in
`agent/src/narratives_agent/workflows/contracts/synthesis.md`: the model
picks one of three cases (direct, related measures, no data) from the
question, the digest, and MISSING DATA. For related measures the opening
names the indicators and what they measure of the topic before any figure,
and claims a measure is missing from Data Commons only when MISSING DATA
names it. Missing measures close the answer under `**Data gaps:**`. No
logic, math, or discovery change.

**Results.**

| Question | `baseline` opening | `after-fit` opening |
|---|---|---|
| P1 women's healthcare access | 0 of 2 completed set the lens: one opened on births attended "held steady, 0 pp", one gave a figure and named the measures after it | 3 of 3 name the indicators and what they cover first ("…through reproductive health services and outcomes rather than laws or funding") |
| P3 India's economy | 0 of 3: straight to GDP growth | 3 of 3 name the indicators first |
| P2 Austin vs Indianapolis | Direct | 2 of 3 name the lens ("a baseline comparison of housing affordability") |
| D1–D3 direct | Source and figure first | Unchanged; no restated question, no Data gaps label |
| N1, N3 no data | Good | Unchanged; "not available in Data Commons" |
| E1 Japan vs France aging | Mixed | Still mixed (2 of 3 lens first) |

- `**Data gaps:**` closed 8 of 8 answers whose discovery reported missing
  measures (0 of 8 used the label before; they used varied lead-ins).
- No "we", "I", "the system", or apology in any answer, before or after.
- Reported values identical across runs; runs differ only in which figures
  they include.
- Speed unchanged (median 64 s before, 67 s after).

**Open items.**

1. P3 run 1 set an indicator list between dashes, which an existing rule
   forbids.
2. When MISSING DATA is empty, whether a question is "broad" is a judgment
   call: P2 and E1 are not classified the same way on every run.
3. N2 (abortion laws) was refused as off-domain by the classifier in 1 of 3
   `baseline` runs and 3 of 3 `after-fit` runs, so it never reaches the
   no-data answer. The classifier is separate from synthesis and was not
   changed.
4. P1 run 2 answered with a cross-country snapshot rather than a five-year
   trend: a discovery choice, not framing.
5. The runner sees discovery's `missing` list, not every note the pipeline
   adds to MISSING DATA, so an occasional Data gaps item cannot be traced.

## 2. Thinking level: medium vs low (`medium-timed` vs `low-thinking`)

**Setup.** Same prompts (with the framing change), same 10 questions × 3
runs, same local agent and data service, run back to back on 2026-11-08.
Low thinking was set for both discovery and synthesis through a temporary
`config/agent-config.json` override, removed afterwards.

### Speed

| Measure (median unless noted) | Medium | Low | Change |
|---|---|---|---|
| Whole turn | 66.5 s | 22.5 s | about 3× faster |
| Whole turn (mean) | 76.2 s | 27.1 s | |
| Question received → synthesis starts (classify, discovery, processing) | 30.4 s | 15.5 s | −15 s |
| **Synthesis (writing the answer)** | **36.4 s** | **3.6 s** | **−33 s** |
| First answer block on screen | 63.1 s | 17.6 s | −45 s |
| Tool calls per turn | 11 | 9 | |

Per question, low was faster on every one: the slowest questions went from
101–118 s (P1, P2, E1) to 24–52 s, and direct questions from 47–67 s to
15–19 s.

**Most of the gain comes from synthesis.** At medium, synthesis thinks for
about half a minute before it writes, and the answer appears only near the
end of the turn. At low, it writes almost at once.

### Quality

| Check | Medium | Low |
|---|---|---|
| Turns completed | 28/30 (2 N2 refusals) | 29/30 (1 N2 refusal) |
| Direct openings (D1–D3) | Source and figure first | Same; word-for-word identical across runs |
| Proxy openings (P1–P3) name the lens first | 8 of 9 (P2 run 3 opened directly) | 8 of 9 (P1 run 2 found no data, below) |
| No-data openings (N1, N3) | "not available in Data Commons" | Same, slightly shorter |
| Figures / charts / citation markers per answer with data | 9.4 / 1.5 / 6.1 | 9.8 / 1.8 / 6.2 |
| Answers with no citation | 0 | 0 |
| `**Data gaps:**` when missing measures were reported | 9/9 | 6/6 |
| Voice slips ("we", "I", "the system") | 0 | 0 |
| Indicator list set between dashes (rule break) | 1 | 2 |
| Same headline values across runs | Yes | Yes |
| Streamed thought characters per turn | about 7,800 | 0 |

Within this set, low-thinking answers are hard to tell apart from medium
ones, as the ad-hoc testing suggested. Low followed the new framing step,
citation, and Data gaps rules as well as medium did.

### The one real failure

**P1 low run 2 ran out of research steps before fetching any data.**
Discovery made 15 searches without a fetch, hit the step limit, and the turn
ended with no data. The user saw "We ran out of research steps…" and an
answer saying data on the topic "is not available in Data Commons", which
is false: the other runs found it. P1 is near the step limit at medium too
(`after-fit` P1 run 2 also ran out, but had fetched data first, so it gave a
partial answer). Low discovery makes this edge more likely and its result
worse.

### Reading the results

- **Synthesis at low** gives about 33 of the 44 seconds saved, with no
  quality loss found here. It is the lower-risk half: the server computes
  every figure, and synthesis only writes.
- **Discovery at low** saves about 15 seconds more, but it decides which
  data the answer gets. Its one failure here is the kind users notice most:
  a false "not available".
- **Thoughts.** At low, no thoughts were streamed in any run (both phases),
  so the thought panel would be empty. If discovery goes low, the proposed
  tool-call progress messages become necessary, not optional. If discovery
  stays medium, its thoughts (and the TMI issue) remain in discovery only.

### Mixed setting: discovery medium, synthesis low (`mixed-thinking`)

Run as a confirmation after the two runs above.

| Median unless noted | Medium / medium | **Medium / low** | Low / low |
|---|---|---|---|
| Whole turn | 66.5 s | **40.1 s** | 22.5 s |
| Whole turn (mean) | 76.2 s | **45.3 s** | 27.1 s |
| Question received → synthesis starts | 30.4 s | 33.1 s | 15.5 s |
| Synthesis | 36.4 s | **3.9 s** | 3.6 s |
| First answer block on screen | 63.1 s | **36.2 s** | 17.6 s |
| Tool calls per turn | 11 | 11 | 9 |
| Streamed thought characters (both phases) | about 7,800 | about 2,600 (discovery) | 0 |
| Turns completed | 28/30 | 27/30 (3 N2 refusals) | 29/30 |
| Proxy openings name the lens first | 8 of 9 | **9 of 9** | 8 of 9 |
| Figures / charts / citation markers per answer with data | 9.4 / 1.5 / 6.1 | 10.6 / 1.6 / 6.4 | 9.8 / 1.8 / 6.2 |
| `**Data gaps:**` when needed | 9/9 | 7/7 | 6/6 |
| Voice slips | 0 | 0 | 0 |
| Indicator list between dashes | 1 | 2 | 2 |
| Ran out of research steps | 0 | P1 twice, both with data | P1 once, with no data |

The mixed setting is about 40% faster than medium (26 s saved per turn,
nearly all of it in synthesis), with discovery making the same number of
tool calls as at medium and no turn left without data. Openings, citations,
charts, and Data gaps matched medium. Discovery still streams thoughts,
about a third as much as at medium.

**Correction: P1 answers were weaker in the mixed and low runs.** P1 asks
about "the last five years". Answers that report a five-year change:
`medium-timed` 3 of 3, `after-fit` 2 of 3, `mixed-thinking` 1 of 3,
`low-thinking` 1 of 3. The others gave a country snapshot, a change "since
2000", or no data. The time window is planned in discovery, and the weaker
answers mostly come from runs that ran out of research steps (below). With
3 runs per setting this may be partly chance, but it is the one quality
difference found.

**P1 and the step limit.** P1 (women's healthcare access, a broad global
question over five years) ran out of research steps in 1 of 3 `after-fit`
runs, 2 of 3 `mixed-thinking` runs, and 1 of 3 `low-thinking` runs, so this
is a property of broad questions under the current step budget rather than
of any one thinking level. Medium discovery fetches data before the limit
and gives a partial answer; low discovery once did not. Worth a separate
look at the discovery budget or prompt.

### Recommendation

1. **Move synthesis to low** (`thinking.synthesis_level: "low"` in
   `defaults/agent-config.json`). The mixed run confirms it: median turn
   66 s → 40 s, answer on screen 27 s sooner, with no writing-quality loss
   found; the weaker P1 answers trace to discovery running out of steps,
   which also happens at medium.
2. **Keep discovery at medium for now.** Low discovery would save another
   18 s, but it is the setting that decides which data the answer gets, and
   its one failure was a false "not available". Test it on a wider set of
   broad questions first, together with the step-limit issue above.
3. **The block-by-block fade-in fits low synthesis**: the answer takes
   about 4 s to write once synthesis starts.
4. **Thought stream.** With discovery at medium, discovery thoughts (and
   the TMI issue) remain, at about a third of today's volume. The tool-call
   progress messages would replace them; that is a separate code change.

### Limits of this test

- 10 questions × 3 runs, one evening, one local machine: enough to see a
  3× speed difference, not enough to rule out rare quality failures.
- Token use was not measured (the stream does not carry it); the drop in
  thought volume and time suggests a large saving.
- The N2 refusals come from the classifier, which runs at its own fixed
  level and was not part of this test.

## 3. Expert session 2 patterns on the current build (`session2-current`)

**Setup.** The 8 questions in `session2_questions.json`, rebuilt from the
second expert session (one per pattern the critic flagged), 2 runs each, on
the current prompts with discovery medium and synthesis low. The session
itself ran on a build older than the editorial pass (#596): its answers
still carried the scatter-chart sentence that #596 removed.

| # | Pattern | Still happens? | Evidence |
|---|---|---|---|
| 1a | Texas vs USA treated as peers ("led by the United States") | **No** | Both runs: "76 dengue cases in Texas compared to 1,944 nationwide", then the two rates side by side |
| 1b | Scatter sentence under a line chart | **No** | Removed in #596 |
| 1c | Brazil's share of the world never given | **Yes** | Both totals given, then "Shares of the total could not be calculated from consistent data." (reads like a system error); run 2 repeats both totals in a table |
| 2 | Definition question answered as missing data | **Yes, milder** | No invented disease list now, but both runs open "While a breakdown … is unavailable" and then report figures, never saying what the indicator measures |
| 3 | Malaria: stacked opening clauses, jargon name | **Half** | Stacking gone (today's framing change); "malaria incidence per 1,000 population at risk" still unexplained |
| 4 | Total vs per-person trend labels | **Yes** | Run 1 labels both a total and a rate bullet `**Long-term trend:**` |
| 5 | "Ten highest include nine states"; truncated "all states" table | **Changed** | Riddle not seen, but the rule that produces it is still in the contract. Run 1 listed all 51 places, run 2 only ten ("the top ten reporting places"): inconsistent, and "reporting places" is a banned term |
| 6 | "Lowest in 2020" when 2020 is the first year asked | **Yes** | Run 1 `**Period low:**` 2020; run 2 "lowest in 2020 and peaked in 2025" |
| 7 | Leaders repeated in headline, bullet, and table | **Mostly no** | Not repeated as a bullet in these runs |

S8 ("all the states", without the conversation context the session had)
asked which country, or reported no data: not comparable to the session.

## 4. Session 2 fixes (`session2-current` → `session2-fixes`)

**Change.** Synthesis contract only: a definition case in the fit step;
plain meanings for technical indicator names; peaks and lows scoped to the
question's window; distinct total and rate trend labels; a new "A place and
the place that contains it" section; the Rankings example that read as a
riddle replaced and "reporting places" banned there; and a new "Tables of
all places" section that lists every place the results hold and never
fills a missing figure. Same setup as `session2-current` (2 runs per
question, discovery medium, synthesis low).

| # | Pattern | Before | After |
|---|---|---|---|
| 1 | Texas vs USA | Counts side by side | "Texas recorded **76** dengue cases, of **1,944** nationwide", then rates side by side, in both runs |
| 1 | Brazil's share | "Shares of the total could not be calculated from consistent data." | "Brazil recorded **212,812,405**, of **8,215,424,893** worldwide … Brazil's share of the world population is not among these figures." (the share itself waits on E3) |
| 2 | Definition question | "While a breakdown … is unavailable", then figures | Both runs open "This United Nations indicator counts the people requiring interventions against neglected tropical diseases from 2010 to 2022, reported as a single combined total" |
| 3 | Malaria jargon | "malaria incidence per 1,000 population at risk" | "new malaria cases per 1,000 people living in areas at risk" in both runs |
| 4 | Total vs rate labels | `**Long-term trend:**` twice | "India trend" and "India rate trend"; "Brazil rate per 1,000 trend" |
| 5 | All-states table | 51 rows once (with filled gaps), 10 rows once | 50 rows in both runs, gaps left empty and named after the table |
| 6 | "Lowest in 2020" | In both runs | Gone in both runs |

**Regression check.** The original 10 questions (`framing-fixes`, 2 runs
each) against `mixed-thinking`: same openings, median 40.2 s (was 40.1 s),
Data gaps 5/5, no voice slips.

**Still open.**

- S6 run 1 still wrote "All reporting states"; run 2 printed table figures
  without thousands separators ("3069856").
- S1 run 1 stacked two opening clauses again ("While … is unavailable,
  according to the NNDSS, …").
- The "all states" table has empty cells until E8 lands.

**Tightening (`session2-tighten`, S1 and S6, 2 runs each).** Three rules
added: at most one introductory clause, with the source inside the main
clause; thousands separators in table cells (years excepted); and no
"reporting" when introducing a table of places.

- Stacked clauses: fixed in both runs ("While annual data before 2016 and
  after 2023 are unavailable, the National Notifiable Diseases Surveillance
  System recorded **76** dengue cases in Texas in 2023, of **1,944**
  nationwide").
- Separators: every table cell formatted in both runs.
- "Reporting": 1 of 2 runs still wrote "The 51 reporting places, which
  include 49 states, the District of Columbia, and Puerto Rico". The
  default synthesis prompt itself described coverage as "how many places
  reported" and gave the example "42 of 54 countries reported this"; both
  are now reworded ("how many places have a value", "have figures for
  2022"), not yet re-run.

## 5. Bullet selection (`session2-bullets`, `framing-bullets`)

**Change.** Synthesis contract only. Bullets are chosen, not inventoried:
each must answer part of the question or add what the headline and other
bullets do not; a fixed priority order (what answers the question, then
where series cross or diverge, then the long-term change, then one notable
peak or low); crossovers only between two given figures for the same date,
with no difference or ratio the digest does not give; places sharing
measures grouped by measure; no two bullets with the same opening; partial
coverage stated as the span covered ("CDC records cover 2016 to 2023")
rather than a list of missing years. The guard stated in the contract:
"Selecting is the only judgment: every figure in a bullet is one the
digest gives, exactly as given." Citation rules unchanged.

| Run | Bullets per answer (mean) | Bullets repeating an opening | Median s |
|---|---|---|---|
| `after-fit` (framing set, 3 runs) | 3.4 | 19 | 66.5 |
| `mixed-thinking` (framing set, 3 runs) | 3.6 | 10 | 40.1 |
| `framing-fixes` (framing set, 2 runs) | 3.5 | 5 | 40.2 |
| `framing-bullets` (framing set, 2 runs) | 3.3 | 3 | 44.0 |
| `session2-fixes` (session set, 2 runs) | 3.1 | 5 | 48.7 |
| `session2-bullets` (session set, 2 runs) | 3.1 | 1 | 48.2 |

Texas vs USA (S1), both runs: "CDC records cover 2016 to 2023: Texas
recorded **76** dengue cases in 2023, out of **1,944** nationwide", the
rates side by side, then three bullets grouped by measure (total trend,
the shared 2021 low, rate trend) in place of four that repeated one
sentence shape. The 2021 crossover the Editor pointed out (Texas's rate
briefly above the national rate) was not selected.

**Figure integrity.** `compare_runs.py` lists every number in the newest
run that no earlier run of the same question contained. 20 such numbers
across both sets; each was checked in context. All are results the
analysis computes (changes, peaks, lows, sharpest declines, a ranking),
several matching figures from other questions on the same data, with one
exception: P3 run 1 gave India's labor force participation as **59.1%**
and **54.4%** where the digest gives the share **0.591** and **0.544**
(earlier runs printed it so). The meaning is unchanged, but the numbers are
rescaled by the writer, which the "exactly as given" rule does not allow.

**Decision: keep the strict rule.** A figure is reported exactly as the
digest gives it; the writer never rescales it. The contract now says so
explicitly ("a share the digest gives as **0.591** stays **0.591**, never
'59.1%'"), and reporting shares as percentages is engineering follow-up E9.

**Still open.** One NTD answer said "Cases peaked" for people requiring
interventions.

## 6. Sources, counted units, and breakdowns (`session2-sources`)

**Change.** Synthesis contract only: name the publishing organization, not
a program, survey, or website; say what an indicator counts when it
differs from the question's word; a general breakdown's lead-in gives the
largest one or two shares exactly as computed, never a summed share; the
digest's unallocated remainder is described as unassigned, not as a
category, right after the table; the breakdown examples no longer carry
the real figures of the questions they illustrate. Chart legends and chart
type for breakdowns are E10.

**Businesses by industry (S9), both runs:** "According to the U.S. Bureau
of Labor Statistics (Quarterly Census of Employment and Wages), the United
States had **12,171,676 business establishments** (individual workplace
locations, not companies) … Health care and social assistance (**15.72%**)
and professional, scientific, and technical services (**13.76%**) make up
the largest shares", and after the table "Nonclassifiable establishments
make up **2.78%**, and the remaining **2.52%** is not assigned to any listed
category." Texas population now cites "the U.S. Census Bureau" in both
runs (earlier: "the Population Estimates Program", "census.gov").

**Regression check** (`framing-sources`, 2 runs): same openings, median
42.8 s, Data gaps 5/5, no voice slips, 1 repeated bullet opening (was 19 in
`after-fit`). Every newly appearing figure across both sets traces to a
computed result (one flag was a year, 2025); S9's figures are identical
across its two runs.

**Older rules that slipped** (computed figures, rule-breaking
presentation):

- A percentage change of a rate already in percent: "the population growth
  rate fell **33.87%** in Brazil" (S2 run 1; run 2 correctly gave **0.196
  percentage points**) and "GDP growth … expanded by **103.26%** overall
  since 1961" (P3 run 1).
- A long-period change of a nominal amount: "GDP per person … up
  **3,081.9%** since 1960" (P3 run 1).
- Causal wording: "Japan is aging faster than France, driven by a
  faster-growing older population" (E1 run 2).

**Trust item: real figures in examples.** Several contract examples carry
real figures from the questions they illustrate (life expectancy in Japan
**84.04 years**, Colorado's **5.9 million**, Ohio's **$71,389**, among
others). An answer that matches them cannot be told apart from one copied
from the example. The breakdown examples are now illustrative; the rest
remain to be replaced.

## 7. Examples without figures (`framing-placeholders`, `session2-placeholders`)

**Change.** Every example figure in the synthesis contract outside the
Citations section, and in the default synthesis prompt, is now a
placeholder that describes it (`**[value]**`, `**[change]**`, `[year]`), so
an answer can never take a figure from an example, and a matching figure
always comes from the digest. Format rules are described in words ("a comma
between each group of three digits"). The Citations section keeps its
sample figures, which its tests check word for word. A contract test fails
if any bold figure returns outside Citations.

**Results** (original 10 questions and S1, S5, S9, S10, 2 runs each): no
placeholder appeared in any answer; openings, Data gaps (4/4), and voice
unchanged; every newly appearing figure traces to a computed result.

**Noted.**

- S10 run 1 reported "**206,803,343.49** adults aged 25 and older" and
  "**82,398,207.17** adults … held at least a bachelor's degree":
  fractional counts of people, from a computed step, reported exactly as
  given. A count of people with decimals erodes trust; see E11.
- Some bullets open with "According to the [source]", which the
  repeated-opening count picks up (7 across the set, from 1).

## 8. Direction, parallel bullets, and units (`session2-direction`, `framing-direction`, `session2-period`, `framing-period`)

**Change.** Synthesis contract only. A question about direction is
answered in words from the computed changes, judging words only when every
change agrees; with three or more indicators the opening carries no figure
and each indicator gets a parallel bullet (change, then latest value); a
unit is given once per bullet; a rate keeps the group its indicator's name
defines ("per 1,000 women aged 15 to 19", never "per 1,000 people"); a
qualifier every gap shares goes in the Data gaps line. Then: the direction
sentence must name its period when it differs from the period asked; no
minus sign after "fell"; no figure turned into a threshold ("over 18%").

**Results.**

- Healthcare (P1), when discovery computed five-year changes: "Across their
  most recent five-year periods, family planning coverage and female life
  expectancy rose, while maternal mortality and adolescent births fell",
  then four parallel bullets, "**40.67 births per 1,000 women aged 15 to
  19**", and "Global figures for these measures are not available in Data
  Commons:".
- Minus signs after "fell": 2 of 23 answers before the sign rule, 0 of 15
  after. Thresholds ("over", "nearly", "about" before a figure): 0 of 15.
- **The period rule did not take.** In 3 of 5 healthcare answers (S11 runs
  1 and 3, P1 run 2) discovery computed changes since 2000, not over five
  years, and the opening still said "maternal mortality fell" without
  naming the period. Making the rule unconditional (always name the period
  in the direction sentence) is the next step; discovery choosing long-term
  windows for a "last five years" question is part of E4.
- **Unconditional period rule** (`session2-period2`, `framing-period2`):
  the direction sentence always names its period. 5 of 5 healthcare
  answers did, including the one where discovery computed long-term
  changes: "between 2000 and their latest reporting dates, modern family
  planning coverage and female life expectancy rose, while maternal
  mortality and adolescent births fell." Two nuances remain: one answer
  named a single period ("Between 2018 and 2024") for indicators whose
  periods differ (maternal mortality 2015 to 2020), and one called all
  three changes "improvements", a judging word the rule allows only when
  every change agrees. Openings still sometimes set the indicator list
  between dashes, which an existing rule forbids.

## 9. Regions and groupings of countries (`region-before` → `region-after` → `region-noguess`)

A participant asked about an indicator in Latin America and got no
results. Question set: `regional_questions.json` (R1–R5: Latin America,
Sub-Saharan Africa, the European Union, South America, and the official
long name "Latin America and the Caribbean"), two runs each per stage.

**Cause.** Data Commons holds a region as a place of its own ("Latin
America" resolves to the UN region `LatinAmericaAndCaribbean`, "South
America" to the continent). A search with the region in `places` returns
only indicators with a figure for the region as a whole, mostly UN SDG
measures, so life expectancy, reported for all 39 member countries but not
for the region, did not appear. Fetching the member countries returns
them. Neither discovery nor the classifier said to treat a region as its
countries, so the agent sometimes stopped at "no data", and sometimes
hunted for another region ID from memory.

**Changes (prompts only).**
- Discovery: for a region, search the region and its member countries in
  parallel in the first round; use a region-wide figure only for a
  one-figure question that has one; otherwise fetch the member countries;
  never report a region unavailable before trying them; use the short
  region name.
- Discovery: the no-guessing rule now covers place DCIDs. Every place DCID
  must come from a search result in the turn (standard `country/` ISO
  DCIDs excepted); when the member countries have no data, report
  unavailable instead of trying other region IDs.
- Classifier: a region or grouping of countries is `child_places`.
- Synthesis: "A region and its countries": lead with a region-wide figure
  when the digest has one; otherwise "across the [count] countries … the
  median was …" with the highest and lowest, never one country standing
  for the region; the region named as the digest names it.

**Results.**

| Measure | before | after (region rule) | noguess (+ place-ID rule) |
|---|---|---|---|
| Answers using a region ID no search returned | 6 of 10 | 2 of 10 (both EU) | 0 of 10 (S4: 0 of 2) |
| Latin America openings (R1, R5) with one country standing for the region | 1 of 4 | 0 of 4 | 0 of 4 |
| Latin America openings (R1, R5) giving the median and the range | 0 of 4 (3 gave the median only) | 4 of 4 | 4 of 4 |
| EU (R3) | never tried members; "not available" | tried members; then guessed IDs | tried members; stopped cleanly (39–42s) |
| South America (R4) opening on what is missing | 2 of 2 | 1 of 2 | 1 of 2 |

Guessed IDs before the fix included `country/LCN`, `wikidataId/Q12585`,
`sdg/021` (the UN code for Northern America), and `Americas` as the parent
of Latin America; none returned data, so no wrong figure reached an
answer, but a wrong region could have. Data check for R3: Data Commons has
no unemployment rate for EU member countries (France returns nothing since
2020; a search offers only labour-force measures), so "not available" is
correct.

**Open.**
- South America trend answers still open on the missing regional series
  in half the runs, once with a 2009 continent figure; the opening wording
  is deferred to a later round on openings.
- R4 lists Panama among South America's countries, as Data Commons places
  it; a data matter, not a prompt one.
- E13 (enforce the place-ID rule in code) and E14 (the long region name,
  for the MCP team).

## Engineering follow-ups

Changes the evaluations point to that need code, outside the prompt-only
scope of this work. Each lists the evidence and what it unlocks.

| # | Change | Evidence | Unlocks |
|---|---|---|---|
| E1 | Pass each indicator's footnote (such as "Includes data from … WHO Global Health Observatory") and definition link (the provenance `descriptionUrl`) to the synthesis prompt; today it receives only the indicator's name and unit | Session 2 definition question; `get_variable_metadata` returns both for `sdg/SH_TRP_INTVN` | Definition answers that name the reporting body and link the official definition |
| E2 | An `indicator_definition` classifier pattern with its own discovery and synthesis directives (`QueryPattern`, `pattern_guidance.py`, `classify.md`) | Session 2 definition question routed to the data template | Definition and methodology questions, often follow-ups, answered as definitions rather than data requests |
| E3 | A share of one place in another (Brazil ÷ World): the composition and derived-metric steps join on the same place | S2: "Shares of the total could not be calculated from consistent data." | Part-to-whole answers with the share the user asked for |
| E4 | Discovery step budget on broad questions | P1 ran out of research steps in 1–2 of 3 runs at every thinking level; low discovery once ended with no data | Broad questions answered in the time window asked |
| E5 | Classifier consistency on legal or policy topics | N2 refused as off-domain in 1–3 of 3 runs per setting | A no-data answer ("not available in Data Commons") instead of a refusal |
| E6 | `line` charts limited to the window the question asks for | Session 2 "lowest in 2020" next to a chart from 1960 | Text and chart scoped to the same years |
| E7 | Thinking levels: synthesis low (proposed in `defaults/agent-config.json`), discovery medium; tool-call progress messages in place of streamed thoughts | Section 2 | Faster answers; no instructions leaking through thoughts |
| E8 | Return every place of a cohort when the question asks for all of them: `rank_cohort` returns at most 25 places from each end (`MAX_RANK_ENTRIES_PER_END = 25`, so 50 at most), and US states with D.C. and Puerto Rico number 51–52. Raise the limit for cohorts up to about 60 places, or add a "list all" option | S6, "all states" table: with the "Tables of all places" rule, both runs leave the same cells empty (Arkansas's count; Oregon's and Kentucky's population), the middle places outside both ends of those rankings. Before the rule, the table filled them: Arkansas **9** = rate × population (calculated by the writer), Oregon **4,233,358** (not in the results; apparently recalled) | "All states" tables with every place and every figure, all computed by the server |
| E9 | Report shares as percentages in the digest when the source gives a fraction (labor force participation as **0.591**), so the writer never has to choose between an unfriendly figure and rescaling it | P3 run 1 (`framing-bullets`) rescaled **0.591** to **59.1%**; the strict rule now keeps **0.591** | Readable shares, every figure exactly as the server computed it |
| E10 | Readable chart legends and a better chart for a single place's breakdown: series labels show raw names ("Count Of BLS Establishment: NAICS/62"), and 20 categories are drawn as vertical bars clustered over one "United States" tick | Business establishments by industry (Editor review) | Charts a reader can use without cross-referencing codes; sorted horizontal bars with category names |
| E11 | Counts of people or things computed with fractions ("**206,803,343.49** adults"): round counts to whole numbers in the analysis output, or flag them, before they reach the writer, which must report figures exactly as given | S10 run 1 (`session2-placeholders`) | Counts readers can trust at a glance |
| E12 | Default trend window of the last ten years when the question names none: today `fetch_observations` for named places fetches the full series ("since 1960") while cohort fetches default to ten years. Set the default in the fetch and analysis window, not the prompt, so text, figures, and chart agree; an explicit range always wins; extend the window for sparse series (fewer than about three points in ten years); word peaks as "highest since [year]" | Japan life expectancy answers reporting change since 1960 | Recent, relevant trends, consistent between named places and cohorts |
| E13 | Refuse a fetch or metadata call for a place DCID that no search returned earlier in the turn (allowing standard `country/` ISO DCIDs), and return an error that tells the model to search for the place. The loop already collects place DCIDs from search results (`mcp_loop.py`, ~L322–338). A prompt rule now forbids guessing, but only code can guarantee it | `region-before`: R1 fetched `country/LCN`, `country/LAC`, `wikidataId/Q12585`, and `sdg/021` (the UN code for Northern America); R5 used `Americas` as the parent of "Latin America". `region-after`: both R3 (EU) runs tried `Europe`, `country/EU`, `dc/g/EuropeanUnion` after the member countries had no data. `session2-bullets` S4 tried `dc/g/LatinAmericaAndTheCaribbean` and `dc/g/Sub-SaharanAfrica` | No answer can describe the wrong region (North America for Latin America); no wasted rounds on guessed IDs |
| E14 | For the MCP team: the official name "Latin America and the Caribbean" fails with "no place found matching name", while "Latin America" resolves to `LatinAmericaAndCaribbean`. Also worth noting: a search with a region in `places` returns only indicators with a figure for the region itself, not those reported by its member countries | R5 (`region-before`), direct MCP checks | Region questions that resolve under the name users and agencies use |

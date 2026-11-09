# Answer framing evaluation

Checks how the synthesis answer frames the data against the question asked,
and whether the same question gets the same answer on repeated runs. It
exercises prompt changes only; the figures come from the server's analytics
and must not change between runs.

## The three cases

| Case | When it applies | Expected opening |
|---|---|---|
| **Direct** | A reported indicator measures what the question names, and MISSING DATA says nothing about it. | Source, year, and the headline figure. No restating of the question. |
| **Proxy** | The question names a broad concept, or its exact measure is in MISSING DATA, and the answer uses related indicators. | A short clause naming the lens the data gives (what the indicators measure), then the figures. No claim of absence that MISSING DATA does not support. |
| **None** | The digest holds no data. | States plainly that the indicator asked about is not available in Data Commons, then what related data exists. |

Any answer with gaps ends with a `**Data gaps:**` label listing what is not
available in Data Commons, taken from MISSING DATA.

## Question set

| ID | Expected case | Question |
|---|---|---|
| D1 | Direct | What is the unemployment rate across US states? |
| D2 | Direct | Compare life expectancy in Japan and France. |
| D3 | Direct | How has the population of Texas changed over time? |
| P1 | Proxy | Has women's access to healthcare globally increased or decreased over the last five years? |
| P2 | Proxy | Is Austin more affordable than Indianapolis? |
| P3 | Proxy | How is India's economy doing? |
| N1 | None | What is the average age of the German population? |
| N2 | None | How many anti-abortion laws were passed globally since 2020? |
| N3 | None | How many public libraries are there in Kenya? |
| E1 | Edge | Is Japan aging faster than France? |

The same list lives in `framing_questions.json`, which the runner reads.

## Checklist per answer

1. **Opening fits the case.** The first sentence follows the expected
   opening above.
2. **No unsupported absence claim.** Anything the answer says is "not
   available" appears in the run's MISSING DATA (the `missing` list, or the
   `report_unavailable` reason and searched indicators), which the runner
   prints beside each answer.
3. **Gaps at the end.** When MISSING DATA is not empty, the answer ends with
   `**Data gaps:**` and lists them; the opening does not list them.
4. **Voice.** No "we", no "I", no "the system", no addressing the reader
   about their question. "Data Commons" is the only name for the data
   service.
5. **Stable figures.** The bold figures are identical across runs of the
   same question.

## Running it

1. Start the agent locally from `narratives/`: `pnpm dev:agent` (needs
   `GEMINI_API_KEY` in `.env.local`).
2. From `narratives/`, run:

   ```sh
   python3 editorial/run_framing_eval.py --label baseline --repeats 3
   ```

   Options: `--url` (default `http://localhost:5001/agent/chat/stream`),
   `--only D1,P1` to run a subset.
3. Read `editorial/runs/<label>/report.md`. It groups the runs of each
   question side by side, with the MISSING DATA and the bold figures of each
   run, and lists for each run the figures the other runs do not all share.
   A different subset of figures is expected; a different value for the
   same measure is a regression. The raw stream of every run is kept in
   `runs.jsonl` in the same folder; `--report-only` rebuilds the report from
   it without running the agent.

Compare a `baseline` run on the current prompts with a run after a prompt
change, question by question, against the checklist. To put saved runs side
by side (completion, speed and phase timings, tool calls, streamed thought
volume, Data gaps, voice, and every opening), run
`python3 editorial/compare_runs.py <label> <label> ...`. Results worth
keeping go in `findings.md`.

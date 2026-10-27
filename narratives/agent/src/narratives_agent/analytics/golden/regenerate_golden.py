# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Builds and checks the golden fixture of the analytics library.

Run `uv run python -m narratives_agent.analytics.golden.regenerate_golden`
from `agent/` to rewrite `core_golden.json`, or pass `--check` to exit
non-zero when the checked-in fixture does not match the current output.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from narratives_agent.analytics.alignment import (
    align_cohort,
    find_unit_mismatch,
)
from narratives_agent.analytics.digest import AnalysisDigest
from narratives_agent.analytics.provenance import (
    AlternativeSource,
    Provenance,
    Source,
)
from narratives_agent.analytics.ranking import rank_cohort
from narratives_agent.analytics.summarize import summarize_table
from narratives_agent.analytics.tables import (
    ObservationRow,
    ObservationTable,
)
from narratives_agent.analytics.timeseries import analyze_timeseries
from narratives_agent.json_value import JsonObject, json_safe

__all__ = ["GOLDEN_PATH", "build_golden_cases", "main", "render_golden"]

GOLDEN_PATH = Path(__file__).with_name("core_golden.json")

_WDI_URL = "https://datatopics.worldbank.org/world-development-indicators/"
_WIKIDATA_URL = "https://www.wikidata.org/wiki/Wikidata:Main_Page"
_WDI_SOURCE = Source(name="datatopics.worldbank.org", url=_WDI_URL)
_WIKIDATA_SOURCE = Source(name="wikidata.org", url=_WIKIDATA_URL)
_ALTERNATIVE_WDI = AlternativeSource(
    facet_id="18369491376878146239",
    provenance_url=_WDI_URL,
    observation_period="P1Y",
)
_ALTERNATIVE_WIKIDATA = AlternativeSource(
    facet_id="12850099660527362240",
    provenance_url=_WIKIDATA_URL,
    measurement_method="WikidataPopulation",
)

_PLACE_NAMES = {
    "country/FRA": "France",
    "country/DEU": "Germany",
    "country/ZWE": "Zimbabwe",
    "country/ARG": "Argentina",
}


def _build_table(
    rows: Sequence[tuple[str, str, float]],
    *,
    names: dict[str, str] | None = None,
    requested_places: Sequence[str] | None = None,
    parent_place_dcid: str | None = None,
    child_place_type: str | None = None,
    facet_id: str = "18369491376878146239",
    source: Source = _WDI_SOURCE,
    unit: str | None = None,
    scaling_factor: float | None = None,
    observation_period: str | None = "P1Y",
    alternative_sources: tuple[AlternativeSource, ...] = (
        _ALTERNATIVE_WIKIDATA,
    ),
) -> ObservationTable:
    """Builds an `ObservationTable` with rows sorted by `(place_dcid, date)`.

    `requested_places` becomes the table's requested places, deduplicated in
    order. Without it, a child-place table (`parent_place_dcid` and
    `child_place_type` set) requests the places in its rows and in `names`,
    and any other table requests no places.
    """
    names = dict(names or {})
    sorted_triples = sorted(rows, key=lambda item: (item[0], item[1]))
    observation_rows = tuple(
        ObservationRow(
            place_dcid=place,
            place_name=names.get(place, place),
            date=date,
            value=value,
            facet_id=facet_id,
        )
        for place, date, value in sorted_triples
    )
    row_places = [row.place_dcid for row in observation_rows]
    if requested_places is not None:
        target_places = tuple(dict.fromkeys(requested_places))
    elif parent_place_dcid and child_place_type:
        target_places = tuple(dict.fromkeys([*row_places, *names]))
    else:
        target_places = ()
    place_names = dict(names)
    for place in [*target_places, *row_places]:
        place_names.setdefault(place, place)
    return ObservationTable(
        variable_dcid="Count_Person",
        variable_name="Total population",
        unit=unit,
        scaling_factor=scaling_factor,
        provenance=Provenance(sources=(source,), facet_ids=(facet_id,)),
        rows=observation_rows,
        requested_places=target_places,
        place_names=place_names,
        parent_place_dcid=parent_place_dcid,
        child_place_type=child_place_type,
        observation_period=observation_period,
        facet_id=facet_id,
        source=source,
        alternative_sources=alternative_sources,
    )


def _build_series_table(
    place: str,
    values: Sequence[tuple[str, float]],
) -> ObservationTable:
    """Builds a single-place series table."""
    return _build_table(
        [(place, date, value) for date, value in values],
        names={place: _PLACE_NAMES[place]},
        requested_places=[place],
    )


def _build_multi_decade_values() -> list[tuple[str, float]]:
    """Returns a 2000 to 2020 series with a 2005 peak and a 2010 trough.

    The series ends at double its starting value.
    """
    return [
        ("2000", 100.0),
        ("2001", 110.0),
        ("2002", 120.0),
        ("2003", 130.0),
        ("2004", 140.0),
        ("2005", 180.0),
        ("2006", 150.0),
        ("2007", 140.0),
        ("2008", 130.0),
        ("2009", 120.0),
        ("2010", 100.0),
        ("2011", 110.0),
        ("2012", 120.0),
        ("2013", 130.0),
        ("2014", 140.0),
        ("2015", 150.0),
        ("2016", 160.0),
        ("2017", 170.0),
        ("2018", 180.0),
        ("2019", 190.0),
        ("2020", 200.0),
    ]


def _build_cohort_table() -> ObservationTable:
    """Builds a ten-country cohort with staggered latest dates.

    Nine countries report 2022, two of them also report 2023, and the tenth
    reports only 2021.
    """
    places = {f"country/C{index}": f"Country {index}" for index in range(10)}
    rows: list[tuple[str, str, float]] = []
    for index, place in enumerate(places):
        if index == 9:
            rows.append((place, "2021", 900.0))
            continue
        rows.append((place, "2022", float((index * 37) % 11) * 100.0))
        if index < 2:
            rows.append((place, "2023", float(index + 1) * 1000.0))
    return _build_table(
        rows,
        names=places,
        facet_id="12850099660527362240",
        source=_WIKIDATA_SOURCE,
        parent_place_dcid="Earth",
        child_place_type="Country",
        alternative_sources=(_ALTERNATIVE_WDI,),
    )


def _build_tied_cohort_table() -> ObservationTable:
    """Builds five places on one date with the values 10, 8, 8, 5, and 5."""
    rows = [
        ("geoId/04", "2022", 5.0),
        ("geoId/02", "2022", 8.0),
        ("geoId/01", "2022", 10.0),
        ("geoId/05", "2022", 5.0),
        ("geoId/03", "2022", 8.0),
    ]
    return _build_table(
        rows,
        names={f"geoId/0{index}": f"State {index}" for index in range(1, 6)},
    )


def _build_sparse_cohort_table() -> ObservationTable:
    """Builds ten requested places of which only three report."""
    places = [f"country/S{index}" for index in range(10)]
    return _build_table(
        [
            (places[0], "2022", 1.0),
            (places[1], "2022", 2.0),
            (places[2], "2022", 3.0),
        ],
        names=dict.fromkeys(places, "Sparse"),
        requested_places=places,
    )


def build_golden_cases() -> JsonObject:
    """Runs every golden case and returns the serialized expectations.

    Returns:
        A JSON object mapping each case name to the serialized output of
        the analytics call that the case runs.
    """
    cases: JsonObject = {}

    single = _build_series_table("country/FRA", [("2023", 68287487.0)])
    cases["timeseries_single_point"] = analyze_timeseries(single).to_dict()

    positive = _build_series_table("country/DEU", _build_multi_decade_values())
    cases["timeseries_multi_decade_positive"] = analyze_timeseries(
        positive
    ).to_dict()
    cases["summary_multi_decade_positive"] = json_safe(
        summarize_table(positive)
    )

    zero_start = _build_series_table(
        "country/ZWE", [("2010", 0.0), ("2015", 25.0), ("2020", 50.0)]
    )
    negative_end = _build_series_table(
        "country/ARG", [("2010", 50.0), ("2015", 10.0), ("2020", -5.0)]
    )
    cases["timeseries_zero_start"] = analyze_timeseries(zero_start).to_dict()
    cases["timeseries_negative_end"] = analyze_timeseries(
        negative_end
    ).to_dict()
    daily_change = _build_series_table(
        "country/FRA", [("2020-03-01", 1.0), ("2020-03-02", 10.0)]
    )
    cases["timeseries_daily_change_under_a_year"] = analyze_timeseries(
        daily_change
    ).to_dict()
    mixed_precision = _build_series_table(
        "country/FRA", [("2020", 5.0), ("2020-01", 50.0)]
    )
    cases["timeseries_mixed_precision"] = analyze_timeseries(
        mixed_precision
    ).to_dict()

    shared = _build_table(
        [
            ("country/FRA", "2020", 67.0),
            ("country/FRA", "2021", 67.5),
            ("country/DEU", "2020", 83.0),
            ("country/DEU", "2021", 83.2),
        ],
        names={"country/FRA": "France", "country/DEU": "Germany"},
        requested_places=["country/FRA", "country/DEU"],
    )
    cases["timeseries_multi_place_shared_date"] = analyze_timeseries(
        shared
    ).to_dict()
    disjoint = _build_table(
        [
            ("country/FRA", "2010", 65.0),
            ("country/FRA", "2011", 65.3),
            ("country/DEU", "2020", 83.0),
            ("country/DEU", "2021", 83.2),
        ],
        names={"country/FRA": "France", "country/DEU": "Germany"},
        requested_places=["country/FRA", "country/DEU"],
    )
    cases["timeseries_multi_place_disjoint_dates"] = analyze_timeseries(
        disjoint
    ).to_dict()

    cohort = _build_cohort_table()
    cases["alignment_prefers_coverage_over_recency"] = json_safe(
        align_cohort(cohort)
    )
    cases["summary_cohort"] = json_safe(summarize_table(cohort))

    cases["ranking_with_ties"] = rank_cohort(
        _build_tied_cohort_table(),
        max_entries_per_end=3,
        focal_places=["geoId/05", "geoId/09"],
    ).to_dict()
    cases["ranking_with_ties_ascending"] = rank_cohort(
        _build_tied_cohort_table(), max_entries_per_end=2, direction="asc"
    ).to_dict()

    sparse = _build_sparse_cohort_table()
    cases["refusal_insufficient_coverage"] = json_safe(align_cohort(sparse))
    cases["refusal_ranking_insufficient_coverage"] = rank_cohort(
        sparse
    ).to_dict()

    empty = _build_table(
        [],
        requested_places=["country/FRA"],
        facet_id="12850099660527362240",
        source=_WIKIDATA_SOURCE,
        observation_period=None,
        alternative_sources=(),
    )
    cases["summary_empty_table"] = json_safe(summarize_table(empty))
    cases["refusal_empty_table_alignment"] = json_safe(align_cohort(empty))
    cases["refusal_empty_table_timeseries"] = analyze_timeseries(
        empty
    ).to_dict()

    dollars = _build_table([("country/FRA", "2022", 1.0)], unit="USDollar")
    euros = _build_table([("country/FRA", "2022", 1.0)], unit="Euro")
    thousands = _build_table(
        [("country/FRA", "2022", 1.0)], unit="USDollar", scaling_factor=1000.0
    )
    cases["refusal_unit_mismatch"] = json_safe(
        find_unit_mismatch(dollars, euros)
    )
    cases["refusal_scaling_mismatch"] = json_safe(
        find_unit_mismatch(dollars, thousands)
    )
    cases["compatible_units"] = json_safe(find_unit_mismatch(dollars, dollars))

    cases["refusal_ranking_invalid_n"] = rank_cohort(
        _build_tied_cohort_table(), max_entries_per_end=0
    ).to_dict()

    digest = AnalysisDigest.from_results(
        (
            analyze_timeseries(positive, step_id="s1"),
            rank_cohort(cohort, max_entries_per_end=3, step_id="s2"),
        ),
        missing_notes=("No county-level series was found for this topic.",),
    )
    cases["digest"] = digest.to_dict()
    cases["digest_prompt"] = digest.format_for_prompt()
    return cases


def render_golden(cases: JsonObject) -> str:
    """Serializes the cases as the exact text of the fixture file.

    Args:
        cases: The case names and their serialized outputs, as returned by
            `build_golden_cases`.

    Returns:
        Indented JSON with sorted keys and a trailing newline, so equal cases
        always render to identical text.
    """
    return json.dumps(cases, indent=2, sort_keys=True, allow_nan=False) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Regenerates the fixture, or checks it when `--check` is given.

    Args:
        argv: The command-line arguments, without the program name. `None`
            reads them from `sys.argv`.

    Returns:
        The process exit status: 0 when the fixture was written or matches
        the current output, and 1 when `--check` finds it missing or out of
        date. `--check` never writes the file.
    """
    parser = argparse.ArgumentParser(
        description="Regenerate or check the analytics golden fixture."
    )
    parser.add_argument(
        "--check",
        dest="is_check_mode",
        action="store_true",
        help="Exit with status 1 when the fixture does not match the code.",
    )
    arguments = parser.parse_args(argv)
    rendered = render_golden(build_golden_cases())
    if arguments.is_check_mode:
        current = (
            GOLDEN_PATH.read_text(encoding="utf-8")
            if GOLDEN_PATH.exists()
            else ""
        )
        if current != rendered:
            print(
                f"{GOLDEN_PATH} is out of date; rerun without --check to "
                "regenerate it and review the diff.",
                file=sys.stderr,
            )
            return 1
        print(f"{GOLDEN_PATH} matches the current code.")
        return 0
    GOLDEN_PATH.write_text(rendered, encoding="utf-8")
    print(f"Wrote {GOLDEN_PATH}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

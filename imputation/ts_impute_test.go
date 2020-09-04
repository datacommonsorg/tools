package imputation

import (
	"testing"
)

func computeMean(s TimeSeries) float64 {
	var mean float64
	for _, v := range s {
		mean += v
	}
	mean = mean / float64(len(s))
	return mean
}

func createOutput(ts TimeSeries, desiredValues []string) TimeSeries {
	out := make(TimeSeries, len(ts)+len(desiredValues))
	for k, v := range ts {
		out[k] = v
	}
	m := computeMean(ts)

	for _, k := range desiredValues {
		out[k] = m
	}
	return (out)
}

func TestMean(t *testing.T) {
	tests := map[string]struct {
		series         TimeSeries
		additionalKeys []string
	}{
		"empty": {
			series:         TimeSeries{},
			additionalKeys: []string{},
		},
		"length 1": {
			series:         TimeSeries{"2003": 42.5},
			additionalKeys: []string{},
		},
		"length 3, years": {
			series: TimeSeries{
				"2003": 42.5,
				"2002": 18.9,
				"1998": 28,
			},
			additionalKeys: []string{"1999", "2000", "2001"},
		},
		"length 3, 4-month gap": {
			series: TimeSeries{
				"2003-02": 42.5,
				"2002-02": 18.9,
				"2003-04": 28,
			},
			// TODO(eftekhari-mhs): edge case : 2002-01 fails currently.
			additionalKeys: []string{"2002-04", "2002-06", "2002-08", "2002-10", "2002-12"},
		},
		"days": {
			series: TimeSeries{
				"2002-03-01": 42.5,
				"2002-02-01": 18.9,
				"2002-02-02": 28,
			},
			additionalKeys: []string{
				"2002-02-03",
				"2002-02-04",
				"2002-02-05",
				"2002-02-06",
				"2002-02-07",
				"2002-02-08",
				"2002-02-09",
				"2002-02-10",
				"2002-02-11",
				"2002-02-12",
				"2002-02-13",
				"2002-02-14",
				"2002-02-15",
				"2002-02-16",
				"2002-02-17",
				"2002-02-18",
				"2002-02-19",
				"2002-02-20",
				"2002-02-21",
				"2002-02-22",
				"2002-02-23",
				"2002-02-24",
				"2002-02-25",
				"2002-02-26",
				"2002-02-27",
				"2002-02-28",
			},
		},
	}
	for label, test := range tests {
		want := createOutput(test.series, test.additionalKeys)
		got, err := FillMean(test.series)
		if err != nil {
			t.Log(label, err)
		}
		if len(got) != len(want) {
			t.Errorf("%s: Size mismatch: FillMean(%v) = %v, want %v",
				label, test.series, got, want)
		}
		for k, v := range got {
			if vw, ok := want[k]; !ok || vw != v {
				t.Errorf("%s: Value mismatch: FillMean(%v) = %v, want %v",
					label, test.series, got, want)
			}
		}
	}
}

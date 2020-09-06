package imputation

import (
	"sort"
	"testing"
)

// computeMeans computes the mean of the given non-empty time series's data.
func computeMean(s TimeSeries) float64 {
	var mean float64
	for _, v := range s {
		mean += v
	}
	mean = mean / float64(len(s))
	return mean
}

// computeMedian computes the median value of the given non-empty time series's data.
func computeMedian(s TimeSeries) float64 {
	values := make([]float64, 0)
	for _, v := range s {
		values = append(values, v)
	}
	sort.Float64s(values)
    if len(values) % 2 == 0{
        return (values[len(values)/2] + values[len(values)/2 -1])/2
    }else{
	    return values[len(values)/2]
    }
}

// createOutput generate a new time series by adding desiredValues as data points and replace
// their value by using the specified algorithm.
func createOutput(ts TimeSeries, desiredValues []string, method string) TimeSeries {
	out := make(TimeSeries, len(ts)+len(desiredValues))
	for k, v := range ts {
		out[k] = v
	}
	switch method {
	case "mean":
		if len(ts) > 0 {
			m := computeMean(ts)
			for _, k := range desiredValues {
				out[k] = m
			}
		}
	case "zero":
		for _, k := range desiredValues {
			out[k] = 0
		}
	case "median":
		if len(ts) > 0 {
			median := computeMedian(ts)
			for _, k := range desiredValues {
				out[k] = median
			}
		}
	}
	return (out)
}

func TestFillNA(t *testing.T) {
	methods := []string{"mean", "zero", "median"}
	for _, m := range methods {
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
                    "1996": 25,
				},
				additionalKeys: []string{"1999", "2000", "2001", "1997"},
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
			want := createOutput(test.series, test.additionalKeys, m)
			got, err := FillNA(test.series, m)
			if err != nil {
				t.Log(label, err)
			}
			if len(got) != len(want) {
				t.Errorf("%s: Size mismatch: FillNA(%v, %v) = %v, want %v",
					label, test.series, m, got, want)
			}
			for k, v := range got {
				if vw, ok := want[k]; !ok || vw != v {
					t.Errorf("%s: Value mismatch: FillNA(%v, %v) = %v, want %v",
						label, test.series, m, got, want)
				}
			}
		}
	}
}

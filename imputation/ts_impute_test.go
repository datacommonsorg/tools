package imputation

import (
	"math"
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
	if len(values)%2 == 0 {
		return (values[len(values)/2] + values[len(values)/2-1]) / 2
	} else {
		return values[len(values)/2]
	}
}

// Values are produced using Python, Pandas linear interpolation method:
func linearInterpolate(date string) TimeSeries {

	// "length 3, years"
	yseries := TimeSeries{
		"1997": 26.500,
		"1999": 25.725,
		"2000": 23.450,
		"2001": 21.175,
	}

	// "length 3, 2-month gap": {
	mseries := TimeSeries{
		"2002-04": 22.833,
		"2002-06": 26.766,
		"2002-08": 30.700,
		"2002-10": 34.633,
		"2002-12": 38.566,
	}
	// days
	dseries := TimeSeries{
		"2002-02-03": 28.537,
		"2002-02-04": 29.074,
		"2002-02-05": 29.611,
		"2002-02-06": 30.148,
		"2002-02-07": 30.685,
		"2002-02-08": 31.222,
		"2002-02-09": 31.759,
		"2002-02-10": 32.296,
		"2002-02-11": 32.833,
		"2002-02-12": 33.370,
		"2002-02-13": 33.907,
		"2002-02-14": 34.444,
		"2002-02-15": 34.981,
		"2002-02-16": 35.518,
		"2002-02-17": 36.055,
		"2002-02-18": 36.592,
		"2002-02-19": 37.129,
		"2002-02-20": 37.666,
		"2002-02-21": 38.203,
		"2002-02-22": 38.740,
		"2002-02-23": 39.277,
		"2002-02-24": 39.814,
		"2002-02-25": 40.351,
		"2002-02-26": 40.888,
		"2002-02-27": 41.425,
		"2002-02-28": 41.962,
	}

	switch len(date) {
	case 4:
		return yseries
	case 7:
		return mseries
	case 10:
		return dseries
	}
	return nil
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
	case "spline1":
		if len(ts) > 2 {
			series := linearInterpolate(desiredValues[0])
			for _, k := range desiredValues {
				out[k] = series[k]
			}
		}
	}
	return (out)
}

func TestFillNA(t *testing.T) {
	methods := []string{"mean", "zero", "median", "spline1"}
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
			"length 3, 2-month gap": {
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
			if m == "spline1" {
				got, err = Interpolate(test.series, 1)
			}
			if err != nil {
				t.Log(label, err)
			}
			if len(got) != len(want) {
				t.Errorf("%s: Size mismatch: Fill%v (%v) = %v, want %v",
					label, m, test.series, got, want)
			}

			for k, v := range got {
				if vw, ok := want[k]; !ok || math.Abs(vw-v) > 0.001 {
					t.Errorf("%s: Value mismatch: Fill%v (%v) = %v, want %v",
						label, m, test.series, got, want)
				}
			}
		}
	}
}

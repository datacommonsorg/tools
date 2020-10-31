package imputation

import (
	"math"
	"sort"
	"testing"
)

// Data structure for storing precomputed values of each interpolation method.
type InterpolateValues struct {
	linear float64
}

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

// createExpectedTimeSeriesFillNA generate a new time series by adding desiredValues as data points and replace
// their value by using the specified algorithm.
func createExpectedTimeSeriesFillNA(ts TimeSeries, desiredValues []string, method string) TimeSeries {
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

// createExpectedTimeSeriesInterpolate generate a new time series by adding desiredValues as data points and replace
// their value using given precomputed values for each method.
func createExpectedTimeSeriesInterpolate(ts TimeSeries, desiredValues map[string]InterpolateValues, method string) TimeSeries {
	out := make(TimeSeries, len(ts)+len(desiredValues))
	for k, v := range ts {
		out[k] = v
	}
	switch method {
	case "linear":
		if len(ts) > 2 {
			for k, v := range desiredValues {
				out[k] = v.linear
			}
		}
	}
	return (out)
}

// Test function for FillNA; possible methods = {mean, median, zero}
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
			"length 3, 1-month gap": {
				series: TimeSeries{
					"2003-02": 42.5,
					"2002-03": 18.9,
					"2003-04": 28,
				},
				additionalKeys: []string{"2002-04", "2002-05", "2002-06",
					"2002-07", "2002-08", "2002-09", "2002-10", "2002-11",
					"2002-12", "2003-01", "2003-03"},
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
			"35days": {
				series: TimeSeries{
					"2020-02-09": 42.5,
					"2020-03-15": 18.9,
					"2020-05-24": 28,
				},
				additionalKeys: []string{
					"2020-04-19",
				},
			},
			"28days": {
				series: TimeSeries{
					"2020-01-02": 42.5,
					"2020-05-21": 18.9,
					"2020-01-30": 28,
				},
				additionalKeys: []string{
					"2020-03-26",
					"2020-02-27",
					"2020-04-23",
				},
			},
			"3months": {
				series: TimeSeries{
					"2020-10-15": 42.5,
					"2020-07-15": 18.9,
					"2020-01-15": 28,
				},
				additionalKeys: []string{
					"2020-04-15",
				},
			},
			"annually": {
				series: TimeSeries{
					"2020-03-05": 42.5,
					"2016-03-05": 18.9,
					"2017-03-05": 28,
				},
				additionalKeys: []string{
					"2019-03-05",
					"2018-03-05",
				},
			},
			"non_ISO8601_format": {
				series: TimeSeries{
					"2020-03-05": 42.5,
					"2016-03-05": 18.9,
					"2017-0305":  28,
				},
				additionalKeys: []string{},
			},
			"multiple_date_formats": {
				series: TimeSeries{
					"2020-03-05": 42.5,
					"2016-03-05": 18.9,
					"2017-03":    28,
				},
				additionalKeys: []string{},
			},
		}
		for label, test := range tests {
			want := createExpectedTimeSeriesFillNA(test.series, test.additionalKeys, m)
			got, err := FillNA(test.series, m)

			if err != nil {
				t.Log(label, err)
			}
			if len(got) != len(want) {
				t.Errorf("%s: Size mismatch: Fill%v (%v) = %v, want %v",
					label, m, test.series, got, want)
			}

			for k, v := range got {
				if vw, ok := want[k]; !ok || vw != v {
					t.Errorf("%s: Value mismatch: Fill%v (%v) = %v, want %v",
						label, m, test.series, got, want)
				}
			}
		}
	}
}

// Test function for Interpolate; possible methods : {linear}
// Values are produced using Python, Pandas linear interpolation method:
func TestInterpolate(t *testing.T) {
	methods := []string{"linear"}
	for _, m := range methods {
		tests := map[string]struct {
			series         TimeSeries
			additionalKeys map[string]InterpolateValues
		}{
			"empty": {
				series:         TimeSeries{},
				additionalKeys: map[string]InterpolateValues{},
			},
			"length 1": {
				series:         TimeSeries{"2003": 42.5},
				additionalKeys: map[string]InterpolateValues{},
			},
			"length 3, years": {
				series: TimeSeries{
					"2003": 42.5,
					"2002": 18.9,
					"1998": 28,
					"1996": 25,
				},
				additionalKeys: map[string]InterpolateValues{
					"1997": {linear: 26.500},
					"1999": {linear: 25.725},
					"2000": {linear: 23.450},
					"2001": {linear: 21.175},
				},
			},
			"length 3, 2-month gap": {
				series: TimeSeries{
					"2003-02": 42.5,
					"2002-02": 18.9,
					"2003-04": 28,
				},
				additionalKeys: map[string]InterpolateValues{
					"2002-04": {linear: 22.833},
					"2002-06": {linear: 26.766},
					"2002-08": {linear: 30.700},
					"2002-10": {linear: 34.633},
					"2002-12": {linear: 38.566},
				},
			},
			"days": {
				series: TimeSeries{
					"2002-03-01": 42.5,
					"2002-02-01": 18.9,
					"2002-02-02": 28,
				},
				additionalKeys: map[string]InterpolateValues{
					"2002-02-03": {linear: 28.537},
					"2002-02-04": {linear: 29.074},
					"2002-02-05": {linear: 29.611},
					"2002-02-06": {linear: 30.148},
					"2002-02-07": {linear: 30.685},
					"2002-02-08": {linear: 31.222},
					"2002-02-09": {linear: 31.759},
					"2002-02-10": {linear: 32.296},
					"2002-02-11": {linear: 32.833},
					"2002-02-12": {linear: 33.370},
					"2002-02-13": {linear: 33.907},
					"2002-02-14": {linear: 34.444},
					"2002-02-15": {linear: 34.981},
					"2002-02-16": {linear: 35.518},
					"2002-02-17": {linear: 36.055},
					"2002-02-18": {linear: 36.592},
					"2002-02-19": {linear: 37.129},
					"2002-02-20": {linear: 37.666},
					"2002-02-21": {linear: 38.203},
					"2002-02-22": {linear: 38.740},
					"2002-02-23": {linear: 39.277},
					"2002-02-24": {linear: 39.814},
					"2002-02-25": {linear: 40.351},
					"2002-02-26": {linear: 40.888},
					"2002-02-27": {linear: 41.425},
					"2002-02-28": {linear: 41.962},
				},
			},
		}
		for label, test := range tests {
			want := createExpectedTimeSeriesInterpolate(test.series, test.additionalKeys, m)
			got, err := Interpolate(test.series, 1)

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

/*
Package imputation implements a library for time series imputation.
The dates in the time series are assumed to be either of the forms of (all have the same format):
"YYYY-MM-DD" or
"YYYY-MM" or
"YYYY"

The imputation library first finds the minimum gap of existing points and then adds new data points with values according to the selected method.
*/
package imputation

import (
	"errors"
	"fmt"
	"log"
	"sort"
	"time"
)

// TimeSeries stores a time series.  Dates are expressed in ISO 8061 format as illustrated in the constants below.
type TimeSeries map[string]float64

// Assume 3 formatting for the dates: daily, monthly, and yearly.
const (
	dayfmt   = "2006-01-02"
	monthfmt = "2006-01"
	yearfmt  = "2006"
)

// dateGapFinder returns the minimum time gap for the given times.
//
// Args:
//   keys: A sorted list of times all with the same format, one of those listed above.
// Returns:
//   1) The time format of the keys.
//   2) The minimum gap between the keys in terms of years, months, and days.
// TODO(eftekhari-mbs): Modify the algorithm to compute a greatest common divisor-like algorithm, not
// just the minimum gap.
// TODO(eftekhari-mhs): add OK, ERR return values and handle errors.
func dateGapFinder(keys []string) (string, int, int, int) {
	var parseFormat string
	switch len(keys[0]) {
	case 4:
		parseFormat = yearfmt
	case 7:
		parseFormat = monthfmt
	case 10:
		parseFormat = dayfmt
	}

	year, month, day := 0, 0, 0

	duration := 1<<31 - 1 // A large number.

	for i := 0; i < len(keys)-1; i++ {
		start, _ := time.Parse(parseFormat, keys[i])
		end, _ := time.Parse(parseFormat, keys[i+1])

		// Calculate total number of days between each two points and compare to minimum gap so far.
		if delta := int(end.Sub(start).Hours() / 24); duration > delta { //TODO: instead of min use GCD
			duration = delta
			y1, M1, d1 := start.Date()
			y2, M2, d2 := end.Date()

			year = int(y2 - y1)
			month = int(M2 - M1)
			day = int(d2 - d1)
		}
	}

	return parseFormat, year, month, day
}

func getSortedKeys(ts TimeSeries) []string {
	keys := make([]string, 0)
	for k, _ := range ts {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}

func getValues(ts TimeSeries) []float64 {
	values := make([]float64, 0)
	for _, v := range ts {
		values = append(values, v)
	}
	return values
}

// FillNA returns TimeSeries with missing datapoints with assigned values according to the selected method.
// Method can be "mean", "median", and "zero".
// TODO(eftekhari-mhs): Handle error cases.
func FillNA(ts TimeSeries, method string) (TimeSeries, error) {
	if len(ts) < 3 {
		log.Printf("There is not enough data to impute.")
		return ts, nil
	}
	keys := getSortedKeys(ts)
	values := getValues(ts)

	parseFormat, yStep, mStep, dStep := dateGapFinder(keys)
	if parseFormat == "" {
		return ts, errors.New("The date format is not ISO 8601.")
	}

	log.Printf("Step is equal to : %v years, %v months, %v days \n", yStep, mStep, dStep)

	// Computing the filling value.
	var fillV float64
	switch method {
	case "mean":
		for _, v := range values {
			fillV += v
		}
		fillV = fillV / float64(len(keys))
	case "zero":
		fillV = 0
	case "median":
		sort.Float64s(values)
		if len(values)%2 == 0 {
			// In case of even length: median = average of two middle values.
			fillV = (values[len(values)/2] + values[len(values)/2-1]) / 2
			log.Printf("Median is %v: for even case", fillV)
		} else {
			fillV = values[len(values)/2]
			log.Printf("Median is %v: for odd case", fillV)
		}
	default:
		return ts, errors.New("The method is unknown.")
	}

	// TODO(eftekhari-mhs): Handle errors.
	startDate, _ := time.Parse(parseFormat, keys[0])
	endDate, _ := time.Parse(parseFormat, keys[len(keys)-1])

	for d := startDate; d.After(endDate) == false; d = d.AddDate(yStep, mStep, dStep) {
		if _, ok := ts[fmt.Sprint(d.Format(parseFormat))]; !ok {
			ts[fmt.Sprint(d.Format(parseFormat))] = fillV
		}
	}
	return ts, nil
}

// Interpolate function's input is a TimeSeries with possible missing datapoints.
// The function returns a Timeseries with no missing dates. Interpolation method is used to fill the values.
// Methods can vary by degree: d = {1} is implemented.
func Interpolate(ts TimeSeries, degree int) (TimeSeries, error) {
	if len(ts) < 3+(degree-1) {
		log.Printf("There is not enough data to impute.")
		return ts, nil
	}

	switch degree {
	case 1:
		return linear(ts)
	default:
		return ts, errors.New("Not implemented yet.")
	}
}

// Linear interpolation; this is eqivalent to Spline degree 1.
func linear(ts TimeSeries) (TimeSeries, error) {
	keys := getSortedKeys(ts)

	parseFormat, yStep, mStep, dStep := dateGapFinder(keys)
	log.Printf("Step is equal to : %v years, %v months, %v days \n", yStep, mStep, dStep)

	//TODO(eftekhari-mhs): Handle errors.
	startDate, _ := time.Parse(parseFormat, keys[0])
	endDate, _ := time.Parse(parseFormat, keys[len(keys)-1])
	// Assuming the time series is the form of {date1 : y1, date2: y2 ,date3 : y3} and y2
	// is the missing value. d21 = date2-date1 and d31 = date3-date1
	var d21, d31, y1, y2, y3 float64
	nextDate := startDate

	for d := startDate; d.After(endDate) == false; d = d.AddDate(yStep, mStep, dStep) {
		if _, ok := ts[fmt.Sprint(d.Format(parseFormat))]; !ok {
			d21 += 1
			// Looking for the next available date (date3) and y3. Store gap in d31.
			if nextDate.Before(d) {
				d31 = d21
				nextDate = d
				for !ok {
					nextDate = nextDate.AddDate(yStep, mStep, dStep)
					_, ok = ts[fmt.Sprint(nextDate.Format(parseFormat))]
					d31 += 1
				}
				y3, _ = ts[fmt.Sprint(nextDate.Format(parseFormat))]
			}

			y2 = ((d21) * (y3 - y1) / (d31)) + y1
			ts[fmt.Sprint(d.Format(parseFormat))] = y2
		} else {
			d21 = 0
			y1, _ = ts[fmt.Sprint(d.Format(parseFormat))]
			// Reset next available date.
			nextDate = startDate
		}
	}
	return ts, nil
}

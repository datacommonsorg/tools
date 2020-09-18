/*
Package imputation implements a library for time series imputation.
The dates in the time series are assumed to be either of the forms of (all have the same format):
"YYYY-MM-DD" or
"YYYY-MM" or
"YYYY"

The imputation library first finds the GCD(gap) of existing points and then adds new data points with values according to the selected method.
*/
package imputation

import (
	"errors"
	"fmt"
	"log"
	"sort"
	"strings"
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

// Greatest common divisor (GCD) of two integer values.
func gcd(a, b int) int {
	for b != 0 {
		t := b
		b = a % b
		a = t
	}
	return a
}

// dateGapFinder returns the greatest common divisor-like time gap for the given times.
//
// Args:
//   keys: A sorted list of times all with the same format, one of those listed above.
// Returns:
//   1) The time format of the keys.
//   2) The GCD (gap between the keys) in terms of years, months, and days.
//   3) OK is True iff the function successfully computed the frequency of data collection.
//   4) Error != nil in case input has multiple date formats or non ISO 8601.
func dateGapFinder(keys []string) (string, int, int, int, bool, error) {
	var parseFormat string
	year, month, day := 0, 0, 0

	switch len(keys[0]) {
	case 4:
		parseFormat = yearfmt
	case 7:
		parseFormat = monthfmt
	case 10:
		parseFormat = dayfmt
	default:
		return parseFormat, year, month, day, false, errors.New("The date format is not ISO 8601.")
	}

	equalMonths := true
	equalDays := true

	if parseFormat != yearfmt {
		for i := 0; i < len(keys)-1; i++ {
			// Return error in case the dates do not have equal formats.
			if len(keys[i+1]) != len(parseFormat) {
				return parseFormat, year, month,
					day, false, errors.New("The dates have multiple formats.")
			}

			md1 := strings.Split(keys[i], "-")
			md2 := strings.Split(keys[i+1], "-")

			if len(md1) != len(md2) {
				return parseFormat, year, month,
					day, false, errors.New("The dates have multiple formats.")
			}
			// Check for unequal months.
			if md1[1] != md2[1] {
				equalMonths = false
			}
			// Check for unequal days (if exists).
			if len(md1) == 3 {
				if md1[2] != md2[2] {
					equalDays = false
				}
			}
		}
	}

	if parseFormat == yearfmt || (equalMonths && equalDays) {
		for i := 0; i < len(keys)-1; i++ {
			if year == 1 {
				// One year is the minimum possible gap in this case.
				break
			}
			start, err1 := time.Parse(parseFormat, keys[i])
			end, err2 := time.Parse(parseFormat, keys[i+1])
			if err1 != nil || err2 != nil {
				return parseFormat, year, month, day, false, errors.New("The date format is not ISO 8601.")
			}

			y1, _, _ := start.Date()
			y2, _, _ := end.Date()
			yGap := int(y2 - y1)

			if i == 0 {
				// Initialize year with the value of the first gap.
				year = yGap
			} else {
				year = gcd(yGap, year)
			}
		}
	} else if parseFormat == monthfmt || equalDays {
		// One month is the minimum possible gap in this case.
		for i := 0; i < len(keys)-1; i++ {
			if month == 1 {
				break
			}
			start, err1 := time.Parse(parseFormat, keys[i])
			end, err2 := time.Parse(parseFormat, keys[i+1])
			if err1 != nil || err2 != nil {
				return parseFormat, year, month, day, false, errors.New("The date format is not ISO 8601.")
			}

			y1, M1, _ := start.Date()
			y2, M2, _ := end.Date()
			yGap := int(y2 - y1)
			mGap := yGap*12 + int(M2-M1)

			if i == 0 {
				// Initialize month with the value of the first gap.
				month = mGap
			} else {
				log.Println(mGap)
				month = gcd(mGap, month)
			}
		}
	} else {
		for i := 0; i < len(keys)-1; i++ {
			// One day is the minimum possible gap in this case.
			if day == 1 {
				break
			}
			start, err1 := time.Parse(parseFormat, keys[i])
			end, err2 := time.Parse(parseFormat, keys[i+1])
			if err1 != nil || err2 != nil {
				return parseFormat, year, month, day, false, errors.New("The date format is not ISO 8601.")
			}

			dGap := int(end.Sub(start).Hours() / 24)
			if i == 0 {
				// Initialize day with the value of the first gap.
				day = dGap
			} else {
				day = gcd(dGap, day)
			}
		}
	}
	if year == 0 && month == 0 && day == 0 {
		return parseFormat, year, month, day, false, nil
	}
	return parseFormat, year, month, day, true, nil
}

func getKeysAndValues(ts TimeSeries) ([]string, []float64) {
	keys := make([]string, 0, len(ts))
	values := make([]float64, 0, len(ts))
	for k, v := range ts {
		keys = append(keys, k)
		values = append(values, v)
	}
	return keys, values
}

// FillNA returns TimeSeries with missing datapoints with assigned values according to the selected method.
// Method can be "mean", "median", and "zero".
func FillNA(ts TimeSeries, method string) (TimeSeries, error) {
	if len(ts) < 3 {
		log.Printf("There is not enough data to impute.")
		return ts, nil
	}
	keys, values := getKeysAndValues(ts)
	sort.Strings(keys)

	parseFormat, yStep, mStep, dStep, ok, err := dateGapFinder(keys)
	if err != nil {
		return ts, err
	}
	if !ok {
		return ts, errors.New("Dates are not annual, monthly, or daily.")
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

	startDate, err1 := time.Parse(parseFormat, keys[0])
	endDate, err2 := time.Parse(parseFormat, keys[len(keys)-1])
	if err1 != nil || err2 != nil {
		return ts, errors.New("The date format is not ISO 8601.")
	}

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
	keys, _ := getKeysAndValues(ts)
	sort.Strings(keys)

	parseFormat, yStep, mStep, dStep, ok, err := dateGapFinder(keys)
	if err != nil {
		return ts, err
	}
	if !ok {
		return ts, errors.New("Dates are not annual, monthly, or daily.")
	}
	log.Printf("Step is equal to : %v years, %v months, %v days \n", yStep, mStep, dStep)

	startDate, err1 := time.Parse(parseFormat, keys[0])
	endDate, err2 := time.Parse(parseFormat, keys[len(keys)-1])
	if err1 != nil || err2 != nil {
		return ts, errors.New("The date format is not ISO 8601.")
	}

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

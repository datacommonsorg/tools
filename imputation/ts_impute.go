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

// Assume 3 formattig for the dates: daily, monthly, and yearly.
const (
	dayfmt   = "2006-01-02"
	monthfmt = "2006-01"
	yearfmt  = "2006"
)

// The diff function returns the minimum gap (will change to GCD) from a given set of data points
// that all have the same format.
// TODO(eftekhari-mhs): add OK, ERR return values and handle errors.
func diff(keys []string, dateFormat string) (int, int, int) {
	year, month, day := 0, 0, 0

	duration := 1000 //A large number.

	sort.Strings(keys)
	for i := 0; i < len(keys)-1; i++ {
		start, _ := time.Parse(dateFormat, keys[i])
		end, _ := time.Parse(dateFormat, keys[i+1])

		// Calculate total number of days.
		if delta := int(end.Sub(start).Hours() / 24); duration > delta { //TODO: instead of min use GCD
			duration = delta
			y1, M1, d1 := start.Date()
			y2, M2, d2 := end.Date()

			year = int(y2 - y1)
			month = int(M2 - M1)
			day = int(d2 - d1)
		}
	}

	return year, month, day
}

// FillMean returns TimeSeries with missing datapoints with value = mean(value of existing points).
// TODO(eftekhari-mhs): Handle error cases.
func FillMean(ts TimeSeries) (TimeSeries, error) {
	if len(ts) < 3 {
		log.Printf("not enough data to impute")
		return ts, nil
	}
	keys := make([]string, 0)
	var mean float64 = 0
	for k, v := range ts {
		keys = append(keys, k)
		mean += v
	}
	mean = mean / float64(len(keys))

	var parseFormat string
	switch len(keys[0]) {
	case 4:
		parseFormat = yearfmt
	case 7:
		parseFormat = monthfmt
	case 10:
		parseFormat = dayfmt
	}

	if parseFormat == "" {
		return ts, errors.New("date format is not ISO 8601")
	}

	yStep, mStep, dStep := diff(keys, parseFormat)

	log.Printf("Step is equal to : %v years, %v months, %v days \n", yStep, mStep, dStep)

	sort.Strings(keys)

	//TODO(eftekhari-mhs): Handle errors.
	startDate, _ := time.Parse(parseFormat, keys[0])
	endDate, _ := time.Parse(parseFormat, keys[len(keys)-1])

	for d := startDate; d.After(endDate) == false; d = d.AddDate(yStep, mStep, dStep) {
		if _, ok := ts[fmt.Sprint(d.Format(parseFormat))]; !ok {
			ts[fmt.Sprint(d.Format(parseFormat))] = mean
		}
	}
	return ts, nil
}

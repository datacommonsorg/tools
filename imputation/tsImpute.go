package main

import (
	"fmt"
	"sort"
	"time"
)

const (
	dayfmt   = "2006-01-02"
	monthfmt = "2006-01"
	yearfmt  = "2006"
)

func diff(keys []string, dateFormat string) (year, month, day int) {
	year, month, day = 0, 0, 0

	duration := 1000 //a large number

	sort.Strings(keys)
	for i := 0; i < len(keys)-1; i++ {
		start, _ := time.Parse(dateFormat, keys[i])
		end, _ := time.Parse(dateFormat, keys[i+1])

		// calculate total number of days
		if delta := int(end.Sub(start).Hours() / 24); duration > delta { //TODO: instead of min use GCD
			duration = delta
			y1, M1, d1 := start.Date()
			y2, M2, d2 := end.Date()

			year = int(y2 - y1)
			month = int(M2 - M1)
			day = int(d2 - d1)
		}
	}

	return
}

func fillMean(s map[string]float64) map[string]float64 {
	if len(s) < 3 {
		return s
	}
	keys := make([]string, 0)
	var mean float64 = 0
	for k, v := range s {
		//fmt.Printf("key: %v, value: %v\n",k,v)
		keys = append(keys, k)
		mean += v
	}
	mean = mean / float64(len(keys))
	//fmt.Printf("unsorted keys: %v\n",keys)

	parseFormat := dayfmt
	switch len(keys[0]) {
	case 4:
		parseFormat = yearfmt
	case 7:
		parseFormat = monthfmt
	}

	yStep, mStep, dStep := diff(keys, parseFormat)

	fmt.Printf("Step is equal to : %v years, %v months, %v days \n", yStep, mStep, dStep)

	startDate, _ := time.Parse(parseFormat, keys[0])
	endDate, _ := time.Parse(parseFormat, keys[len(keys)-1])

	for d := startDate; d.After(endDate) == false; d = d.AddDate(yStep, mStep, dStep) {
		//fmt.Println(d.Format(parseFormat))
		if _, ok := s[fmt.Sprint(d.Format(parseFormat))]; !ok {
			s[fmt.Sprint(d.Format(parseFormat))] = mean
		}
	}
	return s
}

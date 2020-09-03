package main

import (
    "testing"
)

func TestMean(t *testing.T) {
    // test 1 empty series
    series1 := make(map [string]float64)
    want := series1
    got := fillMean(series1)
    if  len(got) != len(want) {
        t.Errorf("Size mismatch: fillMean() = %v, want %v", got, want)
    }
    
    for k,v := range got{
        if vw, ok := want[k]; !ok || vw != v {
            t.Errorf("Value mismatch: fillMean() = %v, want %v", got, want)
        }
    } 
    
    //test 2 small series
    series2 := make(map [string]float64)
    series2["2003"] = 42.5
    want = series2
    got = fillMean(series2)
    if  len(got) != len(want) {
        t.Errorf("Size mismatch: fillMean() = %v, want %v", got, want)
    }
    
    for k,v := range got{
        if vw, ok := want[k]; !ok || vw != v {
            t.Errorf("Value mismatch: fillMean() = %v, want %v", got, want)
        }
    } 
    
    
    //test 3 year gap
    series3 := make(map [string]float64)
    series3["2003"] = 42.5
    series3["2002"] = 18.9
    series3["1998"] = 28
    
    want = make(map [string]float64)
    want["2003"] = 42.5
    want["2002"] = 18.9
    want["1998"] = 28
   
    
    var mean float64 = 0
    for _,v := range series3{
        mean += v
    }
    mean = mean/float64(len(series3))
    
    want["2000"] = mean
    want["2001"] = mean
    want["1999"] = mean
    
    got = fillMean(series3)
    if  len(got) != len(want) {
        t.Errorf("Size mismatch: fillMean() = %v, want %v", got, want)
    }
    
    for k,v := range got{
        if vw, ok := want[k]; !ok || vw != v {
            t.Errorf("Value mismatch: fillMean() = %v, want %v", got, want)
        }
    } 
    
    
    //test 4 month gap
    series4 := make(map [string]float64)
    series4["2003-02"] = 42.5
    series4["2002-02"] = 18.9 //edge case : 2002-01 fails currently
    series4["2003-04"] = 28
    want = make(map [string]float64)
    want["2003-02"] = 42.5
    want["2002-02"] = 18.9
    want["2003-04"] = 28
   
    
    mean = 0
    for _,v := range series4{
        mean += v
    }
    mean = mean/float64(len(series4))
    
    want["2002-04"] = mean
    want["2002-06"] = mean
    want["2002-08"] = mean
    want["2002-10"] = mean
    want["2002-12"] = mean
    want["2002-08"] = mean
    
    got = fillMean(series4)
    if  len(got) != len(want) {
        t.Errorf("Size mismatch: fillMean() = %v, want %v", got, want)
    }
    
    for k,v := range got{
        if vw, ok := want[k]; !ok || vw != v {
            t.Errorf("Value mismatch: fillMean() = %v, want %v", got, want)
        }
    } 
    
    
    //test 5 day gap
    series5 := make(map [string]float64)
    series5["2002-03-01"] = 42.5
    series5["2002-02-01"] = 18.9
    series5["2002-02-02"] = 28
    
    want = make(map [string]float64)
    want["2002-03-01"] = 42.5
    want["2002-02-01"] = 18.9
    want["2002-02-02"] = 28
   
    
    mean = 0
    for _,v := range series5{
        mean += v
    }
    mean = mean/float64(len(series5))
    
    want["2002-02-03"] = mean
    want["2002-02-04"] = mean
    want["2002-02-05"] = mean
    want["2002-02-06"] = mean
    want["2002-02-07"] = mean
    want["2002-02-08"] = mean
    want["2002-02-09"] = mean
    want["2002-02-10"] = mean
    want["2002-02-11"] = mean
    want["2002-02-12"] = mean
    want["2002-02-13"] = mean
    want["2002-02-14"] = mean
    want["2002-02-15"] = mean
    want["2002-02-16"] = mean
    want["2002-02-17"] = mean
    want["2002-02-18"] = mean
    want["2002-02-19"] = mean
    want["2002-02-20"] = mean
    want["2002-02-21"] = mean
    want["2002-02-22"] = mean
    want["2002-02-23"] = mean
    want["2002-02-24"] = mean
    want["2002-02-25"] = mean
    want["2002-02-26"] = mean
    want["2002-02-27"] = mean
    want["2002-02-28"] = mean
    
    got = fillMean(series5)
    if  len(got) != len(want) {
        t.Errorf("Size mismatch: fillMean() = %v, want %v", got, want)
    }
    
    for k,v := range got{
        if vw, ok := want[k]; !ok || vw != v {
            t.Errorf("Value mismatch: fillMean() = %v, want %v", got, want)
        }
    } 
}

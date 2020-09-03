package imputation

//TODO(eftekhari-mhs): Refactor to table-driven tests: https://dave.cheney.net/2019/05/07/prefer-table-driven-tests

import (
    "testing"
    "errors"
)

func computeMean(s TimeSeries) (float64, error){
    if len(s) ==0 {
        //TODO err handling: divison by zero 
        return 0, errors.New("Empty TimeSeries: Can't divide by zero")
    }
    var mean float64
    for _, v := range s {
        mean += v
    }
    mean = mean/float64(len(s))
    return mean, nil
}

func createOutput(ts TimeSeries, desiredValues []string) TimeSeries {
  out := make(TimeSeries, len(ts) + len(desiredValues))
  for k, v := range ts {
    out[k] = v
  }
  m, err := computeMean(ts)
  if err != nil{
    return ts    
  }
    
  for _, k := range(desiredValues) {
     out[k] = m
  }
  return(out)
}

func TestMean(t *testing.T) {
    // test 1 empty series
    series1 := make(map [string]float64)
    want := series1
    got, err := FillMean(series1)
    if err != nil {
        t.Log(err)
    }
    if  len(got) != len(want) {
        t.Errorf("Size mismatch: FillMean() = %v, want %v", got, want)
    }
    
    for k, v := range got {
        if vw, ok := want[k]; !ok || vw != v {
            t.Errorf("Value mismatch: FillMean() = %v, want %v", got, want)
        }
    } 
    
    //test 2 small series
    series2 := TimeSeries{
        "2003": 42.5,
    }
    want = series2
    got, err = FillMean(series2)
    if err != nil {
        t.Log(err)
    }
    
    if  len(got) != len(want) {
        t.Errorf("Size mismatch: FillMean() = %v, want %v", got, want)
    }
    
    for k, v := range got {
        if vw, ok := want[k]; !ok || vw != v {
            t.Errorf("Value mismatch: FillMean() = %v, want %v", got, want)
        }
    } 

    //test 3 year gap
    series3 := TimeSeries{
        "2003" : 42.5,
        "2002" : 18.9,
        "1998" : 28,
    }
    
    want = createOutput(series3, []string{"1999", "2000", "2001"})
    
    got, err = FillMean(series3)
    if err != nil {
        t.Log(err)
    }
    if  len(got) != len(want) {
        t.Errorf("Size mismatch: FillMean() = %v, want %v", got, want)
    }
    
    for k, v := range got {
        if vw, ok := want[k]; !ok || vw != v {
            t.Errorf("Value mismatch: FillMean() = %v, want %v", got, want)
        }
    } 
    
    
    //test 4 month gap
    series4:= TimeSeries{
      "2003-02": 42.5,
      "2002-02": 18.9,
      "2003-04": 28,
    } 
    //TODO(eftekhari-mhs) edge case : 2002-01 fails currently
    want = createOutput(series4, []string{"2002-04", "2002-06", "2002-08", "2002-10", "2002-12"})
    
    got, err = FillMean(series4)
    if err != nil {
        t.Log(err)
    }
    if  len(got) != len(want) {
        t.Errorf("Size mismatch: FillMean() = %v, want %v", got, want)
    }
    
    for k, v := range got {
        if vw, ok := want[k]; !ok || vw != v {
            t.Errorf("Value mismatch: FillMean() = %v, want %v", got, want)
        }
    } 
       
    //test 5 day gap
    series5:= TimeSeries{
        "2002-03-01": 42.5,
        "2002-02-01": 18.9,
        "2002-02-02": 28,
    }
    
    want = createOutput(series5, []string{
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
    })
    
    got, err = FillMean(series5)
    if err != nil {
        t.Log(err)
    }
    if  len(got) != len(want) {
        t.Errorf("Size mismatch: FillMean() = %v, want %v", got, want)
    }
    
    for k, v := range got {
        if vw, ok := want[k]; !ok || vw != v {
            t.Errorf("Value mismatch: FillMean() = %v, want %v", got, want)
        }
    } 
}

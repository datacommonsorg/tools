import pandas as pd


def clean_and_transpose(df):
    """Removes NAs, converts data to Series,
  sorts the columns and changes the index name to date.
  Removes rows before March 1st, 2020 since not much data was available."""
    print("Cleaning and Transposing")
    df = df.apply(pd.Series)
    df = df[sorted(df.columns)]
    df = df.T
    df.index.name = 'date'
    return df


def rename_columns(df, data):
    print("Renaming Columns")
    prev_to_new = {}
    for name in df:
        state = data.loc[data['state_dcid'] == name]
        county = data.loc[data.index == name]

        if len(state):
            prev_to_new[name] = state.iloc[0]['state_name']
        elif len(county):
            prev_to_new[name] = county.iloc[0]['county_name'] + ', ' + county.iloc[0]['state_name']
        else:
            continue

    return df.rename(prev_to_new)


def rename_series(series, data):
    print("Renaming Series")
    prev_to_new = {}
    for name in series.index:
        state = data.loc[data['state_dcid'] == name]
        county = data.loc[data.index == name]

        if len(state):
            prev_to_new[name] = state.iloc[0]['state_name']
        elif len(county):
            prev_to_new[name] = " ".join(county.iloc[0]['county_name'].split()[:-1]) + ', ' + county.iloc[0]['state_name']
        else:
            continue

    return series.rename(prev_to_new)

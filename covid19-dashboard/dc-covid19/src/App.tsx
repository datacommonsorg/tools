/**
 Copyright 2020 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

 https://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 */

import React from 'react';
import ContentFile from './ContentFile.json'
import Configuration from './Configuration.json'
import {filterGeoIdByRegionType, filterJSONByArrayOfKeys} from './Utils'
import {getRealISODatesFromArrayOfDeltaDays} from "./Utils";
import SideNav from "./SideNav";
import Row from "./Row";
import OptionPanel from './OptionPanel'

type State = {
    allData: {}[], // [cases, deaths, population, names]
    selectedRegion: string, // current region selected
    selectedShowTopN: number, // default number of top counties/states to show
    datePicked: string, // current date selected, latest is always default
    availableRegions: {}, // region -> geoId
    datesToPick: string[], // available dates to pick from, example: today, 1 week ago, 1 month ago
}

class App extends React.Component <{}, State> {
    state = {
        allData: [{}, {}, {}, {}],
        selectedRegion: Configuration.DEFAULT_REGION,
        selectedShowTopN: Configuration.DEFAULT_SHOWTOPN,
        datePicked: Configuration.DEFAULT_DATE,
        availableRegions: Configuration.REGIONS,
        datesToPick: []
    }

    refs_: any = {}

    componentDidMount() {
        this.refs_ = this.generateRowReferences()
        const requests = this.fetchData()

        Promise.all(requests).then(responses => {
            responses.forEach((response, index) => {
                response.json().then( json => {
                    // Keep the data stored in the same position, that is: [cases, deaths, population, names]
                    // Make a deep copy of the data stored in this.state.data, and then store the json at the index
                    const currentData = this.state.allData.map(val => val)
                    currentData[index] = json
                    this.setState({allData: currentData})

                    // index 0 contains the 'total-cases' object, which has the dates as keys
                    if (index === 0) {
                        // Get an array of all the dates in the data.
                        const allDates = Object.keys(json)
                        const latestDate = allDates[allDates.length - 1]
                        // Get the deltaDates from the Configuration file.
                        const datesToPick = getRealISODatesFromArrayOfDeltaDays(latestDate, Configuration.DATES)
                        this.setState({datesToPick: datesToPick})
                        // The default date is always the latest date available in the dataset,
                        // which happens to be the last date in the array
                        this.setState({datePicked: datesToPick[datesToPick.length - 1]})
                    }
                })
            })
        })
    }

    /**
     * Creates a reference for each row which allows easy access from the SideNav.
     */
    generateRowReferences = () => {
        let refs_ = {}
        Object.keys(ContentFile).forEach(key => refs_[key] = React.createRef<HTMLDivElement>())
        return refs_
    }

    /**
     * In charge of scrolling to a specific reference in the page.
     * @param event
     */
    handleScrollOnRef = (event) => {
        const ref_ = this.refs_[event.target.id]
        if (ref_.current) {
            ref_.current.scrollIntoView({
                behavior: "smooth",
                block: "nearest"
            })
        }
    }

    /**
     * In charge of changing the state when the region, date or showTopN are updated.
     * @param key
     * @param value
     */
    handleSelectUpdate = (key: string, value: any) =>{
        switch(key){
            case 'selectedRegion':
                this.setState({selectedRegion: value})
                break;
            case 'selectedDate':
                this.setState({datePicked: value})
                break;
            case 'selectedShowTopN':
                this.setState({selectedShowTopN: value})
                break;
        }
    }

    /**
     * Request the data from the server, and store the Promises in that order.
     * The order is important [cases, deaths, population, places].
     */
    fetchData = () => {
        const url: string = `http://localhost/api/`
        const apis = [
            url + 'total-cases',
            url + 'total-deaths',
            url + 'population',
            url + 'places'
        ];
        // Map every url to the promise of the fetch
        return apis.map(api => fetch(api));
    }

    getDataOnlyForSelectedRegionType = (data: {}[], selectedRegion: string): {}[]=> {
        let output: {}[] = []
        const geoIdsContainedInSelectedRegion = filterGeoIdByRegionType(data[3], selectedRegion)
        for (let dataSet of this.state.allData.slice(0, 2)){
            let filteredDataSet = {}
            for (let date in dataSet){
                filteredDataSet[date] = filterJSONByArrayOfKeys(dataSet[date], geoIdsContainedInSelectedRegion)
            }
            output.push(filteredDataSet)
        }

        output.push(filterJSONByArrayOfKeys(data[2], geoIdsContainedInSelectedRegion))
        output.push(filterJSONByArrayOfKeys(data[3], geoIdsContainedInSelectedRegion))

        return output
    }
    
    render = () => {
        const data = this.getDataOnlyForSelectedRegionType(this.state.allData, this.state.selectedRegion)
        const rows = Object.keys(ContentFile).map(panelId => <Row allData={data}
                                                                  panelId={panelId}
                                                                  datePicked={this.state.datePicked}
                                                                  region={this.state.selectedRegion}
                                                                  ref_={this.refs_[panelId]}
                                                                  selectedShowTopN={this.state.selectedShowTopN}/>)

        return (
            <div className={"container"}>
                <SideNav handleScrollOnRef={this.handleScrollOnRef}/>
                <div className={"main-content"}>
                    <h1 className={"main-title"}>
                        {Configuration.TITLE + ' '}
                        <span style={{color: "#990001"}}>{Configuration.SUBTITLE}</span>
                    </h1>
                    <OptionPanel handleSelectUpdate={this.handleSelectUpdate}
                                 defaultShowTopN={this.state.selectedShowTopN}
                                 datesToPick={this.state.datesToPick}
                                 defaultDate={this.state.datePicked}
                                 availableRegions={this.state.availableRegions}
                                 defaultRegion={this.state.selectedRegion}/>
                        {rows}
                </div>
                <h5 className={"footer"}>{Configuration.FOOTER}</h5>
            </div>
        )
    }
}

export default App;

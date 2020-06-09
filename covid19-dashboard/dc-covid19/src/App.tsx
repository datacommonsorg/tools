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
import OptionPanel from './OptionPanel'
import SideNav from "./SideNav";
import Row from "./Row";
import PanelInfo from './PanelInfo.json'
import Configuration from './Configuration.json'
import {getRealISODatesFromArrayOfDeltaDays} from "./Utils";

type stateType = {
    data: any, // [cases, deaths, population, names]
    selectedRegion: string, // current region selected
    selectedShowTopN: number, // default number of top counties/states to show
    datePicked: string, // current date selected, latest is always default
    availableRegions: {}, // region -> geoId
    datesToPick: string[], // available dates to pick from, example: today, 1 week ago, 1 month ago
    availableShowTopN: number[], // available numbers to view, example: Top 10, Top 20, Top 30
}

class App extends React.Component <{}, stateType> {

    state = {
        data: [{}, {}, {}, {}],
        selectedRegion: Configuration.DEFAULT_REGION,
        selectedShowTopN: Configuration.DEFAULT_SHOWTOPN,
        datePicked: Configuration.DEFAULT_DATE,
        availableRegions: Configuration.REGIONS,
        datesToPick: [],
        availableShowTopN: Configuration.SHOWTOPN,
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
                    const currentData = this.state.data.map(val => val)
                    currentData[index] = json
                    this.setState({data: currentData})

                    // index 0 contains the 'total-cases' object, which has the dates as keys
                    if (index === 0) {
                        // Get an array of all the dates in the data.
                        const allDates = Object.keys(json)
                        const latestDate = allDates[allDates.length - 1]
                        // Get the deltaDates from the Configuration file.
                        const datesToPick = getRealISODatesFromArrayOfDeltaDays(latestDate, Configuration.DATES)
                        this.setState({datesToPick: datesToPick})
                        console.log(datesToPick)
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
        const refs_ = {}
        Object.keys(PanelInfo).forEach(key => refs_[key] = React.createRef<HTMLDivElement>())
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
    handleSelectUpdate = (key: string, value) =>{
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
        const url: string = `/api/`
        const apis = [
            url + 'total-cases',
            url + 'total-deaths',
            url + 'population',
            url + 'places'
        ];

        // Map every url to the promise of the fetch
        return apis.map(api => fetch(api));
    }
    
    render() {
        const rows = Object.keys(PanelInfo).map(panelId => <Row data={this.state.data}
                                                                panelId={panelId}
                                                                ISOSelectedDate={this.state.datePicked}
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
                                 availableShowTopN={this.state.availableShowTopN}
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

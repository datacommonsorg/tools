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
import getISODatesBasedOnDeltaDates from "./GetAllAvailableDates";

type stateType = {
    data: any, // [cases, deaths, population, names]
    selectedRegion: string, // current region selected
    selectedShowTopN: number, // default number of top counties/states to show
    selectedDate: string, // current date selected, latest is always default
    availableRegions: {}, // region -> geoId
    availableDates: string[], // available dates to pick from, example: today, 1 week ago, 1 month ago
    availableShowTopN: number[], // available numbers to view, example: Top 10, Top 20, Top 30
    rows: JSX.Element[]
}

class App extends React.Component <{}, stateType> {

    state = {
        data: [{}, {}, {}, {}],
        selectedRegion: Configuration.DEFAULT_REGION,
        selectedShowTopN: Configuration.DEFAULT_SHOWTOPN,
        selectedDate: Configuration.DEFAULT_DATE,
        availableRegions: Configuration.REGIONS,
        availableDates: [],
        availableShowTopN: Configuration.SHOWTOPN,
        rows: []
    }

    refs_: any = {}

    componentDidMount() {
        this.refs_ = this.generateRowReferences()
        const requests = this.sendRequest()

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
                        const availableDates = getISODatesBasedOnDeltaDates(latestDate, Configuration.DATES)
                        this.setState({availableDates: availableDates})
                        // The default date is always the latest date available in the dataset, which happens
                        // to be the last date in the array
                        this.setState({selectedDate: availableDates[availableDates.length - 1]})
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
                this.setState({selectedDate: value})
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
    sendRequest = () => {
        const host = window.location.protocol + '//' + window.location.hostname
        const url: string = `${host}/api/`
        let urls = [
            url + 'total-cases',
            url + 'total-deaths',
            url + 'population',
            url + 'places'
        ];

        // Map every url to the promise of the fetch
        return urls.map(url => fetch(url, {mode: 'cors'}));
    }
    
    render() {
        const rows = Object.keys(PanelInfo)
            .map(panelId => <Row data={this.state.data}
                                panelId={panelId}
                                ISOSelectedDate={this.state.selectedDate}
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
                                 availableDates={this.state.availableDates}
                                 availableRegions={this.state.availableRegions}
                                 defaultShowTopN={this.state.selectedShowTopN}
                                 defaultDate={this.state.selectedDate}
                                 defaultRegion={this.state.selectedRegion}/>
                        {rows}
                </div>
                <h5 className={"footer"}>{Configuration.FOOTER}</h5>
            </div>
        )
    }
}

export default App;

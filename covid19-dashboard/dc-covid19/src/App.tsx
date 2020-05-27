import React from 'react';
import OptionPanel from './OptionPanel'
import SideNav from "./SideNav";
import Row from "./Row";
import PanelInfo from './PanelInfo.json'
import Configuration from './Configuration.json'

type stateType = {
    allData: {}, // copy of all the unparsed data
    selectedRegion: string, // current region selected
    selectedShowTopN: number, // default number of top counties/states to show
    selectedDate: string, // current date selected, latest is always default
    availableRegions: {}, // region -> geoId
    availableDates: {}, // id -> ISOdate
    availableShowTopN: number[], // available numbers to view, example: Top 10, Top 20, Top 30
    rows: JSX.Element[],
    dcidMap: {}, // converts geoId to the region's name
    animationClassName: string // will be passed down as a prop to anything requiring an animation
}

class App extends React.Component <{}, stateType> {
    constructor(props: {}) {
        super(props);
        // Create the references for quick sidenav onClick
        this.refs_ = this.generateRefs()
        // On-load fadein animation.
        this.fadeInAnimation()
        // Request latest data from server.
        this.sendRequest().then(r => console.log("Data has been loaded!"))
    }

    state = {
        allData: {},
        selectedRegion: Configuration.DEFAULT_REGION,
        selectedShowTopN: Configuration.DEFAULT_SHOWTOPN,
        selectedDate: Configuration.DEFAULT_DATE,
        availableRegions: Configuration.REGIONS,
        availableDates: Configuration.DATES,
        availableShowTopN: Configuration.SHOWTOPN,
        rows: [],
        dcidMap: {},
        animationClassName: "fadeInAnimation"
    }

    refs_: any = {}

    generateRefs = () => {
        const refs_ = {}
        Object.keys(PanelInfo).forEach(key => refs_[key] = React.createRef<HTMLDivElement>())
        return refs_
    }

    /**
     * Sets the fadeInAnimation.
     */
    fadeInAnimation = () => {
        this.setState({animationClassName: "fadeInAnimation"})
        window.setTimeout(() => {
            this.setState({animationClassName: ""})
        }, 1000)
    }

    /**
     * In charge of scrolling to a specific reference in the document.
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
     * Sends AJAX request to get all the data from the server.
     * Stores the dates, dcidMap (converts geoId to name) and all the data.
     */
    sendRequest = async () => {
        const host = window.location.protocol + '//' + window.location.hostname
        const url: string = `${host}/get-all-data`
        await fetch(url, {mode: 'cors'}).then(response => response.json().then(res => {
            this.setState({availableDates: res['availableDates']})
            this.setState({availableRegions: {...this.state.availableRegions,...res['availableRegions']}})
            this.setState({dcidMap: res['dcidMap']})
            this.setState({allData: res})
        }))
    }
    
    render() {
        const rows = Object.keys(PanelInfo)
            .map(dataId => <Row data={this.state.allData}
                                typeOfData={dataId}
                                selectedDate={this.state.selectedDate}
                                ISOSelectedDate={this.state.availableDates[this.state.selectedDate]}
                                region={this.state.selectedRegion}
                                ref_={this.refs_[dataId]}
                                loading={Object.keys(this.state.allData).length === 0}
                                dcidMap={this.state.dcidMap}
                                selectedShowTopN={this.state.selectedShowTopN}
                                animationClassName={this.state.animationClassName}/>)

        return (
            <div className={"container " + this.state.animationClassName}>
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

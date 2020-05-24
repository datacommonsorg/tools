import React from 'react';
import OptionPanel from './OptionPanel'
import SideNav from "./SideNav";
import Row from "./Row";
import numberWithCommas from "./NumberWithCommas";
import moment from 'moment'
import PanelInfo from './PanelInfo.json'

type dataHolder = {
    label: string,
    value: number,
    absolute: number
}

type casesAndDeathsHolder = {
    cases: dataHolder[],
    deaths: dataHolder[]
}

type stateType = {
    allData: {},
    region: string,
    selectedDate: string,
    availableDates: {
        latest: string,
        sevenDays: string,
        fourteenDays: string,
        thirtyDays: string,
    }
    availableRegions: {state: string, county: string},
    showTopN: number,
    daily: casesAndDeathsHolder,
    dailyPerCapita: casesAndDeathsHolder,
    dailyIncrease: casesAndDeathsHolder,
    weekly: casesAndDeathsHolder,
    weeklyPerCapita: casesAndDeathsHolder,
    weeklyIncrease: casesAndDeathsHolder,
    monthly: casesAndDeathsHolder,
    monthlyPerCapita: casesAndDeathsHolder,
    monthlyIncrease:  casesAndDeathsHolder,
    absoluteCumulative: casesAndDeathsHolder,
    cumulativePerCapita: casesAndDeathsHolder,
    dcidMap: {},
    animationClassName: string
}

let casesAndDeaths = {cases: [], deaths: []}
class App extends React.Component <{}, stateType> {
    constructor(props: {}) {
        super(props);
        // On-load fadein animation.
        this.fadeInAnimation()
        // Request latest data from server.
        this.sendRequest().then(r => console.log("Data has been loaded!"))
    }

    state = {
        allData: {}, // copy of all the unparsed data
        region: "state", // current region selected
        showTopN: 10, // number of top counties/states to show
        selectedDate: "latest", // current date selected
        availableRegions: {
            state: "All States",
            county: "All Counties"
        },
        availableDates: { // get the latest dates from server, these will be overwritten to the actual date once the server responds.
            latest: "Latest",
            sevenDays: "1 Week Ago",
            fourteenDays: "2 Weeks Ago",
            thirtyDays: "1 Month Ago",
        },
        daily: casesAndDeaths,
        dailyPerCapita: casesAndDeaths,
        dailyIncrease: casesAndDeaths,
        weekly: casesAndDeaths,
        weeklyPerCapita: casesAndDeaths,
        weeklyIncrease: casesAndDeaths,
        monthly: casesAndDeaths,
        monthlyPerCapita: casesAndDeaths,
        monthlyIncrease: casesAndDeaths,
        absoluteCumulative: casesAndDeaths,
        cumulativePerCapita: casesAndDeaths,
        dcidMap: {}, // converts geoId to the region's name.
        animationClassName: "fadeInAnimation" // will be passed down as a prop to anything requiring an animation.
    }

    myRefs: {} = {
        daily: React.createRef<HTMLDivElement>(),
        dailyPerCapita: React.createRef<HTMLDivElement>(),
        dailyIncrease: React.createRef<HTMLDivElement>(),

        weekly: React.createRef<HTMLDivElement>(),
        weeklyPerCapita: React.createRef<HTMLDivElement>(),
        weeklyIncrease: React.createRef<HTMLDivElement>(),

        monthly: React.createRef<HTMLDivElement>(),
        monthlyPerCapita: React.createRef<HTMLDivElement>(),
        monthlyIncrease: React.createRef<HTMLDivElement>(),

        absoluteCumulative: React.createRef<HTMLDivElement>(),
        cumulativePerCapita: React.createRef<HTMLDivElement>()
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
        let myRefs = this.myRefs[event.target.id]
        if (myRefs.current) {
            myRefs.current.scrollIntoView({
                behavior: "smooth",
                block: "nearest"
            })
        }
    }

    /**
     * Handles the region state change.
     * This parameter is passed down as a prop to OptionPanel.
     * @param newRegion
     */
    onRegionChange = (newRegion: "state" | "county") => {
        this.state.region = newRegion
        this.parseData(this.state.allData)
    }

    /**
     * Handles the date state change.
     * This parameter is passed down as a prop to OptionPanel.
     * @param newDate
     */
    onDateChange = (newDate: "latest" | "sevenDays" | "fourteenDays" | "thirtyDays") => {
        this.state.selectedDate = newDate
        this.parseData(this.state.allData)
    }

    /**
     * Handles the show state change.
     * This parameter is passed down as a prop to OptionPanel.
     * @param newShow
     */
    onShowChange = (newShow: number) => {
        this.state.showTopN = newShow
        this.parseData(this.state.allData)
    }

    /**
     * Sends AJAX request to get all the data from the server.
     * Stores the dates, dcidMap (converts geoId to name) and all the data.
     */
    sendRequest = async () => {
        const host = window.location.protocol + '//' + window.location.hostname
        const url: string = `${host}/get-all-data`
        await fetch(
            url, {mode: 'cors'}
        ).then(response => response.json().then(res => {
            this.setState({availableDates: res['availableDates']})
            if (res['availableRegions']) this.setState({availableRegions: {'state': 'All States', 'county': 'All Counties', ...res['availableRegions']}})
            this.setState({dcidMap: res['dcidMap']})
            this.setState({allData: res})
            this.parseData(res)
        }))
    }

    /**
     * Converts the data which is a hashmap, into an array so that the chart understands the data.
     * @param data
     */
    parseData(data: {}) {
        // Iterate through all the types of data for the selected date and region.
        // If "state" and "latest" is selected, all the latest data for all "states" would be parsed.
        let typesOfData = data[this.state.selectedDate][this.state.region];
        for (let type in typesOfData) {
            let unparsedData = typesOfData[type]
            let tempData: casesAndDeathsHolder = {
                // There are two types of data, cases and deaths.
                // They all have the same charts, but different data to show.
                // For example, Cases Per Capita and Deaths Per Capita
                cases: this.jsonToArray(unparsedData['cases']),
                deaths: this.jsonToArray(unparsedData['deaths'])
            }
            this.saveData(type, tempData)
        }
    }

    /**
     * Store each data to its corresponding day.
     * Example, store the daily data returned from the server to the daily data in the State.
     * @param key
     * @param data
     */
    saveData = (key: string, data: casesAndDeathsHolder) => {
        // The switch statement makes sure that only valid keys are stored.
        switch(key){
            case "daily":
                this.setState({daily: data})
                break;
            case "dailyPerCapita":
                this.setState({dailyPerCapita: data})
                break;
            case "dailyIncrease":
                this.setState({dailyIncrease: data})
                break;
            case "weekly":
                this.setState({weekly: data})
                break;
            case "weeklyPerCapita":
                this.setState({weeklyPerCapita: data})
                break;
            case "weeklyIncrease":
                this.setState({weeklyIncrease: data})
                break;
            case "monthly":
                this.setState({monthly: data})
                break;
            case "monthlyPerCapita":
                this.setState({monthlyPerCapita: data})
                break;
            case "monthlyIncrease":
                this.setState({monthlyIncrease: data})
                break;
            case "absoluteCumulative":
                this.setState({absoluteCumulative: data})
                break;
            case "cumulativePerCapita":
                this.setState({cumulativePerCapita: data})
                break;
        }
    }

    /**
     * The chart takes a labelList. Which is a list of strings that will be shown on top of each bar.
     * This will pre-generate those strings.
     * For example, if the chart is a percent chart, we want to generate +800 (12%).
     * @param value
     * @param absolute
     * @param population
     */
    getLabelListLabel = (value, absolute, population) => {
        if (absolute && population) return numberWithCommas(absolute) + ' / ' + numberWithCommas(population)
        else if (absolute && value) return "+" + numberWithCommas(absolute) + " (" + ( value) + "%)"
        else return numberWithCommas(value)
    }

    /**
     * Converts an ISO date to English date.
     * For example, 2020-01-01 is converted to January 1st, 2020.
     * @param date
     */
    prettifyDate = (date: string) => {
        if (date.toLowerCase() === "latest") return "Daily"
        else return moment(date).format('MMMM Do, YYYY');
    }

    /**
     * Given a hashmap of data, convert it to a list dataHolder objects.
     * Also sorts the list so that the chart shows the regions from highest to lowest.
     * This is necessary as Chart.jsx only know how to interpret a dataHolder list.
     * @param data
     */
    jsonToArray(data): dataHolder[]{
        let dataAsList: any = []
        let dcids: string[] = Object.keys(data['value'])
        dcids.forEach(dcid => {
            let regionName: string = this.state.dcidMap[dcid]
            let value: number = Math.round(data?.value[dcid] * 100000) / 100000
            let absolute: number = data?.absolute?.[dcid]
            let population: number = data?.population?.[dcid]
            dataAsList.push({
                regionName: regionName,
                value: value,
                absolute: absolute,
                population: population,
                dcid: dcid,
                labelListLabel: this.getLabelListLabel(value, absolute, population)
            })
        })
        return dataAsList.sort((a, b) => b.value - a.value).slice(0, this.state.showTopN)
    }

    /**
     * If the key is 'daily', 'weekly' or 'monthly', or 'absoluteCumulative' return the new sectionTitle.
     * @param dataId
     */
    createNewSection(dataId){
        let newSectionTitle;
        switch(dataId){
            case 'daily':
                newSectionTitle = this.prettifyDate(this.state.availableDates[this.state.selectedDate])
                break;
            case 'weekly':
                newSectionTitle = "Since Last Week"
                break;
            case 'monthly':
                newSectionTitle = "Since Last Month"
                break;
            case 'absoluteCumulative':
                newSectionTitle = "All-Time Cumulative"
                break;
        }
        return newSectionTitle
    }

    /**
     * Gets the panel configuration to pass as a prop to Panel.jsx.
     * @param dataId
     */
    getPanelConfig(dataId: string){
        let newSectionTitle = this.createNewSection(dataId)
        return {
            animationClassName: this.state.animationClassName,
            ref_: this.myRefs[dataId],
            data: this.state[dataId],
            dcidMap: this.state.dcidMap,
            region: this.state.region,
            show: this.state.showTopN,
            title: PanelInfo[dataId].title,
            subtitle: PanelInfo[dataId].subtitle,
            sectionTitle: newSectionTitle
        }
    }
    
    render() {
        console.log(this.state.availableRegions)
        let rows: JSX.Element[] = Object.keys(PanelInfo).map(key => <Row config={this.getPanelConfig(key)}/>)
        return (
            <div className={"container " + this.state.animationClassName}>
                <SideNav handleScrollOnRef={this.handleScrollOnRef}
                         selectedDate={this.state.selectedDate}/>
                <div className={"main-content"}>
                    <h1 className={"main-title"}>
                        Data Commons
                        <span style={{color: "#990001"}}> COVID-19</span>
                    </h1>
                    <OptionPanel onRegionChange={this.onRegionChange}
                                 onDateChange={this.onDateChange}
                                 onShowTopNSelectChange={this.onShowChange}
                                 availableDates={this.state.availableDates}
                                 availableRegions={this.state.availableRegions}/>
                        {rows}
                </div>
                <h5 className={"footer"}>
                    Data from The New York Times, based on reports from state and local health agencies.
                </h5>
            </div>
        )
    }
}

export default App;

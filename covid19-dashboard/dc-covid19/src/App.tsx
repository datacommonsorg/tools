import React from 'react';
import OptionPanel from './OptionPanel'
import SideNav from "./SideNav";
import Row from "./Row";
import numberWithCommas from "./NumerWithCommas";

type dataHolder = {label: string, value: number, absolute: number}
type casesAndDeathsHolder = {cases: dataHolder[], deaths: dataHolder[]}
let casesAndDeaths = {cases: [], deaths: []}
type stateType = {
    allData: {},
    region: string,
    date: string,
    show: number,
    dates: {
        latest: string,
        sevenDays: string,
        fourteenDays: string,
        thirtyDays: string,

    }
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

class App extends React.Component <{}, stateType> {
    constructor(props: {}) {
        super(props);
        this.sendRequest().then(r => console.log("Data has been loaded!"))
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

    animationChange = () => {
        /**
         * Sets the animation on load.
         * TODO: figure out why getting rid of this method breaks the text on top of the bars.
         */
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
        /**
         */
        let myRefs = this.myRefs[event.target.id]
        if (myRefs.current) {
            myRefs.current.scrollIntoView({
                behavior: "smooth",
                block: "nearest"
            })
        }
    }

    state = {
        allData: {}, // copy of all the unparsed data
        region: "state", // current region selected
        date: "latest", // current date selected
        show: 10, // number of top counties/states to show
        dates: { // get the latest dates from server, these will be overwritten to the actual date once the server responds.
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
        dcidMap: {}, // converts geoId to the region's name
        animationClassName: "" // will be passed down as a prop to anything requiring an animation
    }

    /**
     * Handles the region state change.
     * This parameter is passed down as a prop to OptionPanel.
     * @param newRegion
     */
    onRegionChange = (newRegion: "state" | "county") => {
        this.animationChange()
        this.state.region = newRegion
        this.parseData(this.state.allData)
    }

    /**
     * Handles the date state change.
     * This parameter is passed down as a prop to OptionPanel.
     * @param newDate
     */
    onDateChange = (newDate: "latest" | "evenDays" | "fourteenDays" | "thirtyDays") => {
        this.animationChange()
        this.state.date = newDate
        this.parseData(this.state.allData)
    }

    /**
     * Handles the show state change.
     * This parameter is passed down as a prop to OptionPanel.
     * @param newShow
     */
    onShowChange = (newShow: number) => {
        this.animationChange()
        this.state.show = newShow
        this.parseData(this.state.allData)
    }

    /**
     * Sends AJAX request to get all the data from the server.
     * Stores the dates, dcidMap (converts geoId to name) and all the data.
     */
    sendRequest = async () => {
        const host = window.location.protocol + '//' + window.location.hostname
        const url: string = `${host}/get-all-data`
        let response = await fetch(
            url, {mode: 'cors'}
        ).then(response => response.json().then(res => {
            this.setState({dates: res['dates']})
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
        let typesOfData = data[this.state.date][this.state.region];
        for (let type in typesOfData) {
            let unparsedData = typesOfData[type]
            let tempData: casesAndDeathsHolder = {
                // There are two types of data, cases and deaths.
                // They all have the same charts, but different data to show.
                // For example, Cases Per Capita and Deaths per Capita
                cases: this.jsonToArray(unparsedData['cases']),
                deaths: this.jsonToArray(unparsedData['deaths'])
            }
            this.saveData(type, tempData)
        }
    }

    /**
     * Store each data to its corresponding day.
     * That is, store the daily data returned from the server to the daily data in the State.
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
    prettifyDate = (date) => {
        if (date.toLowerCase() === "latest") return "Daily"
        const months = {
            1: "January",
            2: "February",
            3: "March",
            4: "April",
            5: "May",
            6: "June",
            7: "July",
            8: "August",
            9: "September",
            10: "October",
            11: "November",
            12: "December"
        }
        const tempDate = new Date(date)
        let day = tempDate.getDate() + 1
        let month = tempDate.getMonth() + 1
        let year = tempDate.getFullYear()

        return `${months[month]} ${day}th, ${year}`
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
        return dataAsList.sort((a, b) => b.value - a.value).slice(0, this.state.show)
    }

    render() {
        return (
            <div className={"container"}>
                <SideNav handleScrollOnRef={this.handleScrollOnRef} date={this.state.date}/>
                <div className={"main-content"}>
                    <h1 style={{textAlign: "center"}} className={"main-title"}>Data Commons<span style={{color: "#990001"}}> COVID-19</span></h1>
                    <OptionPanel onRegionChange={this.onRegionChange} onDateChange={this.onDateChange} onShowChange={this.onShowChange} dates={this.state.dates}/>
                    <Row animation={this.state.animationClassName} sectionTitle={this.prettifyDate(this.state.dates[this.state.date])} ref_={this.myRefs['daily']} dcidMap={this.state.dcidMap} casesTitle={"Daily Cases"} deathsTitle={"Daily Deaths"} subtitle={""} data={this.state.daily} region={this.state.region} show={this.state.show}/>
                    <Row animation={this.state.animationClassName} sectionTitle={""} ref_={this.myRefs['dailyPerCapita']} dcidMap={this.state.dcidMap} casesTitle={"Daily Cases Per Capita"} deathsTitle={"Daily Deaths Per Capita"} subtitle={"Cases Per 10,000 People"} data={this.state.dailyPerCapita} region={this.state.region} show={this.state.show}/>
                    <Row animation={this.state.animationClassName} sectionTitle={""} ref_={this.myRefs['dailyIncrease']} dcidMap={this.state.dcidMap} casesTitle={"Daily Cases Increase"} deathsTitle={"Daily Deaths Increase"} subtitle={"In Percent"} data={this.state.dailyIncrease} region={this.state.region} show={this.state.show}/>
                    <Row animation={this.state.animationClassName} sectionTitle={"Since Previous Week"} ref_={this.myRefs['weekly']} dcidMap={this.state.dcidMap} casesTitle={"Total Week Cases"} deathsTitle={"Total Week Deaths"} subtitle={""} data={this.state.weekly} region={this.state.region} show={this.state.show}/>
                    <Row animation={this.state.animationClassName} sectionTitle={""} ref_={this.myRefs['weeklyPerCapita']} dcidMap={this.state.dcidMap} casesTitle={"Total Week Cases Per Capita"} deathsTitle={"Total Week Deaths Per Capita"} subtitle={"Cases Per 10,000 People"} data={this.state.weeklyPerCapita} region={this.state.region} show={this.state.show}/>
                    <Row animation={this.state.animationClassName} sectionTitle={""} ref_={this.myRefs['weeklyIncrease']} dcidMap={this.state.dcidMap} casesTitle={"Increase of Cases From Last Week"} deathsTitle={"Increase of Deaths From Last Week"} subtitle={"In Percent"} data={this.state.weeklyIncrease} region={this.state.region} show={this.state.show}/>
                    {// Two months ago there was no COVID19 data per county, so if the user has selected 30 days ago. Don't show monthly data.
                        this.state.date === "thirtyDays" || <Row animation={this.state.animationClassName} sectionTitle={"Since Previous Month"} ref_={this.myRefs['monthly']} dcidMap={this.state.dcidMap} casesTitle={"Total Monthly Cases"} deathsTitle={"Total Monthly Deaths"} subtitle={""} data={this.state.monthly} region={this.state.region} show={this.state.show}/>}
                        {this.state.date === "thirtyDays" || <Row animation={this.state.animationClassName} sectionTitle={""} ref_={this.myRefs['monthlyPerCapita']} dcidMap={this.state.dcidMap} casesTitle={"Total Monthly Cases Per Capita"} deathsTitle={"Total Monthly Deaths Per Capita"} subtitle={"Cases Per 10,000 People"} data={this.state.monthlyPerCapita} region={this.state.region} show={this.state.show}/>}
                        {this.state.date === "thirtyDays" || <Row animation={this.state.animationClassName} sectionTitle={""} ref_={this.myRefs['monthlyIncrease']} dcidMap={this.state.dcidMap} casesTitle={"Increase of Cases From Last Month"} deathsTitle={"Increase of Deaths From Last Month"} subtitle={"In Percent"} data={this.state.monthlyIncrease} region={this.state.region} show={this.state.show}/>}
                    <Row animation={this.state.animationClassName} sectionTitle={"All-Time Cumulative"} ref_={this.myRefs['absoluteCumulative']} dcidMap={this.state.dcidMap} casesTitle={"Cumulative Cases"} deathsTitle={"All-Time Cumulative Deaths"} subtitle={""} data={this.state.absoluteCumulative} region={this.state.region} show={this.state.show}/>
                    <Row animation={this.state.animationClassName} sectionTitle={""} ref_={this.myRefs['cumulativePerCapita']} dcidMap={this.state.dcidMap} casesTitle={"Cumulative Cases Per Capita"} deathsTitle={"All-Time Cumulative Deaths Per Capita"} subtitle={"Cases Per 10,000 People"} data={this.state.cumulativePerCapita} region={this.state.region} show={this.state.show}/>
                </div>
                <h5 className={"footer"}>Data from The New York Times, based on reports from state and local health agencies.</h5>
            </div>
        )
    }
}

export default App;

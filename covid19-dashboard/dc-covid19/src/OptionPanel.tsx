import React, {ChangeEvent} from "react";
type Props = {
    handleSelectUpdate: (key: string, value: string | number) => void,
    availableDates: {},
    availableRegions: {},
    availableShowTopN: number[],
    defaultShowTopN: number,
    defaultRegion: string,
    defaultDate: string
}

export default class OptionPanel extends React.Component<Props> {
    handleSelect = (e: ChangeEvent) => {
        const newSelection: string = (e.target as HTMLInputElement).value
        const id: string = (e.target as HTMLInputElement).id
        if (newSelection !== 'empty') this.props.handleSelectUpdate('selected'+ id, newSelection)

    }

    render() {
        const showTopNOptions: JSX.Element[] = this.props.availableShowTopN.map(
            n => <option value={n}>Top {n}</option>)

        // If county, then add a space after it
        const regionOptions: JSX.Element[] = Object.keys(this.props.availableRegions).map(region => {
            if (region === 'county') {
                return (
                <React.Fragment>
                    <option value={region}>{this.props.availableRegions[region]}</option>
                    <option value={'empty'}/>
                </React.Fragment>)
            } else {
                return <option value={region}>{this.props.availableRegions[region]}</option>
            }
        })

        // Sort all available dates
        const sortedDates: string[]= Object.keys(this.props.availableDates)
            .sort((a, b) =>
                (this.props.availableDates[a] > this.props.availableDates[b]) ? -1 :
                    ((this.props.availableDates[a] < this.props.availableDates[b]) ? 1 : 0))

        // Get all the date options
        const dateOptions: JSX.Element[]  = sortedDates
            .map(date => <option value={date}>{this.props.availableDates[date]}</option>)

        return (
            <div className={"option-panel panel shadow"}>
                <select className="dropdown shadow" onChange={this.handleSelect} id={"ShowTopN"} defaultValue={this.props.defaultShowTopN}>
                    {showTopNOptions}
                </select>
                <select className="dropdown shadow" onChange={this.handleSelect} id={"Region"} defaultValue={this.props.defaultRegion}>
                    {regionOptions}
                </select>
                <select className="dropdown shadow" onChange={this.handleSelect} id={"Date"} defaultValue={this.props.defaultDate}>
                    {dateOptions}
                </select>
            </div>
        )
    }
}
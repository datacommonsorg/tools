import React, {ChangeEvent} from "react";
import Regions from './Regions.json'
export default class OptionPanel extends React.Component<{ onRegionChange, onDateChange, onShowTopNSelectChange, availableDates }, any> {
    /**
     * Function triggered when the date is changed.
     * @param e
     */
    handleDateSelect = (e: ChangeEvent) => {
        let newSelection: string = (e.target as HTMLInputElement).value
        this.props.onDateChange(newSelection)
    }

    /**
     * Function triggered when the region is changed.
     * @param e
     */
    handleRegionSelect = (e: ChangeEvent) => {
        let newSelection: string = (e.target as HTMLInputElement).value
        this.props.onRegionChange(newSelection)
    }

    /**
     * Function triggered when the show is changed.
     * Remember, show is the number of top counties/states to show.
     * @param e
     */
    handleShowTopNSelect = (e: ChangeEvent) => {
        let newSelection: string = (e.target as HTMLInputElement).value
        this.props.onShowTopNSelectChange(newSelection)
    }

    render() {
        const dates: JSX.Element[] = Object.keys(this.props.availableDates).map(date =>
            <option value={date}>{this.props.availableDates[date]}</option>)

        const regions: JSX.Element[] = Object.keys(Regions).map(region =>
            <option value={region}>{Regions[region]}</option>)

        const showTopN: JSX.Element[] = [5, 10, 20, 30, 40, 50].map(n => <option value={n}>Top {n}</option>)

        return (
            <div className={"option-panel panel shadow"}>
                <select className="dropdown shadow" onChange={this.handleDateSelect}>
                    {dates}
                </select>
                <select className="dropdown shadow" onChange={this.handleRegionSelect}>
                    {regions}
                </select>
                <select className="dropdown shadow" onChange={this.handleShowTopNSelect} defaultValue={10}>
                    {showTopN}
                </select>
            </div>
        )
    }
}
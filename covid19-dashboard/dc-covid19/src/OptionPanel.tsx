import React, {ChangeEvent} from "react";

export default class OptionPanel extends React.Component<{onRegionChange, onDateChange, onShowChange, dates}>{
    /**
     * Function triggered when the date is changed.
     * @param e
     */
    handleDateSelect = (e: ChangeEvent) => {
        let newSelection = (e.target as HTMLInputElement).value
        this.props.onDateChange(newSelection)
    }

    /**
     * Function triggered when the region is changed.
     * @param e
     */
    handleRegionSelect = (e: ChangeEvent) => {
        let newSelection = (e.target as HTMLInputElement).value
        this.props.onRegionChange(newSelection)
    }

    /**
     * Function triggered when the show is changed.
     * Remember, show is the number of top counties/states to show.
     * @param e
     */
    handleShowSelect = (e: ChangeEvent) => {
        let newSelection = (e.target as HTMLInputElement).value
        this.props.onShowChange(newSelection)
    }

    render() {
        return (
            <div className={"option-panel panel shadow"}>
                <select className="dropdown shadow" onChange={this.handleDateSelect}>
                    <option value="latest">{this.props.dates.latest}</option>
                    <option value="sevenDays">{this.props.dates.sevenDays}</option>
                    <option value="fourteenDays">{this.props.dates.fourteenDays}</option>
                    <option value="thirtyDays">{this.props.dates.thirtyDays}</option>
                    </select>
                <select className="dropdown shadow" onChange={this.handleRegionSelect}>
                    <option value="state">States</option>
                    <option value="county">Counties</option>
                </select>
                <select className="dropdown shadow" onChange={this.handleShowSelect} defaultValue={10}>
                    <option value="5">Top 5</option>
                    <option value="10">Top 10</option>
                    <option value="20">Top 20</option>
                    <option value="30">Top 30</option>
                </select>
                </div>
        )
    }
}
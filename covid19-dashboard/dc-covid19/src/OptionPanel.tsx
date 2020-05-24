import React, {ChangeEvent} from "react";
type Props = {onRegionChange, onDateChange, onShowTopNSelectChange, availableDates, availableRegions?}
export default class OptionPanel extends React.Component<Props, any> {
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
        if (newSelection !== 'empty') this.props.onRegionChange(newSelection)
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
        const showTopNOptions: JSX.Element[] = [5, 10, 20, 30].map(n =>
            <option value={n}>Top {n}</option>)

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

        const sortedDates: string[]= Object.keys(this.props.availableDates)
            .sort((a, b) =>
                (this.props.availableDates[a] > this.props.availableDates[b]) ? -1 :
                    ((this.props.availableDates[a] < this.props.availableDates[b]) ? 1 : 0))

        const dateOptions: JSX.Element[]  = sortedDates.map(date => <option value={date}>{this.props.availableDates[date]}</option>)

        return (
            <div className={"option-panel panel shadow"}>
                <select className="dropdown shadow" onChange={this.handleShowTopNSelect} defaultValue={10}>
                    {showTopNOptions}
                </select>
                <select className="dropdown shadow" onChange={this.handleRegionSelect} defaultValue={"state"}>
                    {regionOptions}
                </select>
                <select className="dropdown shadow" onChange={this.handleDateSelect} defaultValue={"latest"}>
                    {dateOptions}
                </select>
            </div>
        )
    }
}
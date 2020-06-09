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

import React, {ChangeEvent} from "react";

type Props = {
    handleSelectUpdate: (key: string, value: string | number) => void,
    datesToPick: string[],
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
        this.props.handleSelectUpdate('selected'+ id, newSelection)
    }

    render() {
        const showTopNOptions: JSX.Element[] = this.props.availableShowTopN.map(n =>
            <option value={n}>Top {n}</option>)

        const regionOptions: JSX.Element[] = Object.keys(this.props.availableRegions).map(region =>
            <option value={region}>{this.props.availableRegions[region]}</option>)


        // Reverse the datesToPick because we want to go show from most recent to oldest
        const dateOptions: JSX.Element[] = this.props.datesToPick.reverse().map(date =>
            <option value={date}>{date}</option>)

        return (
            <div className={"option-panel panel shadow"}>
                <select className="dropdown shadow"
                        onChange={this.handleSelect}
                        id={"ShowTopN"}
                        defaultValue={this.props.defaultShowTopN}>
                    {showTopNOptions}
                </select>
                <select className="dropdown shadow"
                        onChange={this.handleSelect}
                        id={"Region"}
                        defaultValue={this.props.defaultRegion}>
                    {regionOptions}
                </select>
                <select className="dropdown shadow"
                        onChange={this.handleSelect}
                        id={"Date"}
                        defaultValue={this.props.defaultDate}>
                    {dateOptions}
                </select>
            </div>
        )
    }
}
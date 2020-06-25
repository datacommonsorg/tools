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
import Configuration from './Configuration.json'

type Props = {
    handleSelectUpdate: (key: string, value: string | number) => void,
    datesToPick: string[],
    availableRegions: {},
    defaultShowTopN: number,
    selectedRegion: string,
    datePicked: string,
    geoIdToName: {geoId: string} | {}
}

export default function OptionPanel(props: Props) {

    const handleSelect = (e: ChangeEvent) => {
        const newSelection: string = (e.target as HTMLInputElement).value
        const id: string = (e.target as HTMLInputElement).id
        props.handleSelectUpdate(id, newSelection)
    }

    const showTopNOptions: JSX.Element[] = Configuration.SHOWTOPN.map(n => <option key={n} value={n}>Top {n}</option>)
    const regionOptions: JSX.Element[] = Object.keys(props.availableRegions).map(region =>{
        let regionName = props.geoIdToName[region]?.[0]

        // If the region is 'All Counties' and 'All States'
        if (!region.includes('geoId/')) regionName = props.availableRegions[region]

        return <option key={region} value={region}>{regionName}</option>
    })

    const dateOptions: JSX.Element[] = [...props.datesToPick].reverse().map(date =>
        <option key={date} value={date}>{date}</option>)

    return (
        <div className={"option-panel panel shadow"}>
            <select className="dropdown shadow"
                    onChange={handleSelect}
                    id={"showTopN"}
                    defaultValue={props.defaultShowTopN}>
                {showTopNOptions}
            </select>
            <select className="dropdown shadow"
                    onChange={handleSelect}
                    id={"region"}
                    defaultValue={props.selectedRegion}>
                {regionOptions}
            </select>
            <select className="dropdown shadow"
                    onChange={handleSelect}
                    id={"date"}
                    defaultValue={props.datePicked}>
                {dateOptions}
            </select>
        </div>
    )
}
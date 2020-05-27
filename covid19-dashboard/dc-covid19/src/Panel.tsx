import React from "react";
import BarGraphPanel from "./BarGraphPanel";
import EmptyPanel from "./EmptyPanel";
import {LineChart} from "recharts";
import LineGraph from "./LineGraph";
import LineGraphPanel from "./LineGraphPanel";

type Props = {
    typeOfGraph: 'bar' | 'line',
    data: {},
    label: string,
    region: string,
    dcidMap: {},
    selectedDate: string,
    selectedShowTopN: number,
    typeOfData: string
}

export default function Panel(props: Props) {
    /**
     * Decides what type of Panel to show.
     * There are three types of panels, BarGraphPanel, EmptyPanel and LineGraphPanel (coming soon).
     */
    if (props.typeOfGraph === 'bar') {
        return <BarGraphPanel dcidMap={props.dcidMap}
                              data={props.data}
                              selectedDate={props.selectedDate}
                              label={"cases"}
                              region={props.region}
                              selectedShowTopN={props.selectedShowTopN}
                              typeOfData={props.typeOfData}/>
    } else if (props.typeOfGraph === 'line'){
        return <LineGraphPanel dcidMap={props.dcidMap}
                               data={props.data}
                               selectedDate={props.selectedDate}
                               label={"cases"}
                               region={props.region}
                               selectedShowTopN={props.selectedShowTopN}
                               typeOfData={props.typeOfData}/>
    } else {
        return (<EmptyPanel reason={Object.keys(props.data).length === 0 ? 'loading' : 'nan'}/>)
    }
}
import React from "react";
import Chart from './Chart'

type dataHolder = {
    regionName: string,
    value: number,
    absolute: number,
    population: number,
    dcid: string,
    labelListLabel: string
}

type Props = {
    title: string,
    subtitle: string,
    data: dataHolder[],
    label: string,
    region: string,
    dcidMap: {},
    selectedShowTopN: number,
    loading: boolean
}

export default function Panel(props: Props) {
    // If cases, the color of the graph is red.
    // If deaths, the color is grey.
    const color: string = props.label === 'cases' ? '#990001' : 'grey'

    // If the data has been loaded, show the carts
    if (props.data.length > 0) {
        return (
            <div className={"panel chart shadow"}>
                <h4 className={"title"}>{props.title}</h4>
                <h6 className={"title"}>{props.subtitle}</h6>
                <Chart dcidMap={props.dcidMap}
                       label={props.label}
                       data={props.data}
                       region={props.region}
                       color={color}
                       selectedShowTopN={props.selectedShowTopN}/>
            </div>
        )
        
    // If the data hasn't finished loading, then showing an empty panel.
    } else {
        return (
            <div style={{paddingRight: 0}} className={"panel chart shadow empty-panel"}>
                <h2 className={"empty-panel"}>{props.loading ? "Loading..." : "No Data To Display"}</h2>
            </div>
        )
    }
}

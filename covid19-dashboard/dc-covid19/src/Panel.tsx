import React from "react";
import Chart from './Chart'

type dataHolder = {regionName: string, value: number, absolute: number, population: number, dcid: string, labelListLabel: string}
type Props = {title: string, subtitle: string, data: dataHolder[], label: string, region: string, dcidMap: {}, showTopN: number, loading: boolean}
export default function Panel(props: Props) {
    // If cases, the color of the graph is red.
    // If deaths, the color is grey.
    let color: string = props.label === 'cases' ? '#990001' : 'grey'


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
                       showTopN={props.showTopN}/>
            </div>
        )
    // If the data hasn't finished loading, then showing a "Loading..." panel.
    } else if (props.loading) {
        return (
            <div className={"panel chart shadow"}>
                <h2 style={{
                    color: 'grey',
                    marginTop: 50,
                    fontWeight: 'normal',
                    textAlign: 'center'
                }}>Loading...</h2>
            </div>
        )
    } else {
        return (
            <div className={"panel chart shadow"}>
                <h2 style={{
                    color: 'grey',
                    marginTop: 50,
                    fontWeight: 'normal',
                    textAlign: 'center'
                }}>No Reported {props.label}</h2>
            </div>
        )
    }

}
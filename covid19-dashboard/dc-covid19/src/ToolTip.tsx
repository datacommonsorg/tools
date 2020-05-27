import numberWithCommas from "./NumberWithCommas";
import ToolTipContent from "./ToolTipContent";
import React from "react";

type Props = {
    data: dataHolder,
    typeOfChart: string,
    label: string
}

type dataHolder = {
    regionName: string,
    value: number,
    absolute: number,
    population: number,
    dcid: string,
    labelListLabel: string
}

export default function ToolTip(props: Props) {
    let disclaimer: string = ''
    let texts: string[] = []
    if (props.data.dcid === 'geoId/3651000' || props.data.dcid === 'geoId/2938000')
        disclaimer = `All counties in ${props.data.regionName} are combined and reported as one.`

    if (props.typeOfChart === 'perCapita'){
        texts = [`${props.data.value} ${props.label} per 10,000 people`,
            `New ${props.label}: ${numberWithCommas(props.data.absolute)}`,
            `Total population: ${numberWithCommas(props.data.population)} people`]
    } else if (props.typeOfChart === 'percent'){
        texts = [`Percent increase: ${numberWithCommas(props.data.value)}%`,
            `Absolute increase: ${numberWithCommas(props.data.absolute)} ${props.label}`]
    } else {
        texts = [`${numberWithCommas(props.data.value)} ${props.label}`]
    }
    return (<ToolTipContent chartInfo={texts} disclaimer={disclaimer}/>);
}
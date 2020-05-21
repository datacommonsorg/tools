import Panel from "./Panel";
import React from "react";

type Props = {ref_: any, dcidMap: {},
    sectionTitle: string,
    casesTitle: string,
    deathsTitle: string,
    subtitle: string,
    data: {},
    region: string,
    show: number,
    animation: string
}

/**
 * Each row has two panels, where each panel contains a chart.
 * Each panel is either cases or deaths.
 * @param props
 * @constructor
 */
export default function Row(props: Props) {
    return (
        <div className={"row"} ref={props.ref_}>
            {props.sectionTitle &&
            <h1 className={"section-title"}>{props.sectionTitle}</h1>}
            {props.sectionTitle && <hr style={{width: '100%'}}/>}
            <div className={"left"}>
                <Panel dcidMap={props.dcidMap} title={props.casesTitle} subtitle={props.subtitle}
                       animation={props.animation}
                       data={props.data['cases']} label={"cases"} region={props.region}
                       show={props.show}/>
            </div>
            <div className={"right"}>
                <Panel dcidMap={props.dcidMap} title={props.deathsTitle} subtitle={props.subtitle}
                       animation={props.animation}
                       data={props.data['deaths']} label={"deaths"} region={props.region}
                       show={props.show}/>
            </div>
        </div>
    )
}
import Panel from "./Panel";
import React from "react";

type Props = {
    sectionTitle?: string,
    config: any
}

/**
 * Each row has two panels, where each panel contains a chart.
 * Each panel is either cases or deaths.
 * @param props
 * @constructor
 */
export default function Row(props: Props) {
    return (
        <div className={"row"}
             ref={props.config.ref_}>
            {// If there is a section title, then show the text.
                props.config.sectionTitle && <h1 className={"section-title"}>{props.config.sectionTitle}</h1>}
            {// If there is a section title, then show a separator line as well.
                props.config.sectionTitle && <hr style={{width: '100%'}}/>}
            <div className={"left"}>
                <Panel dcidMap={props.config.dcidMap}
                       title={props.config.title.replace("{TYPE}", "Cases")}
                       subtitle={props.config.subtitle.replace("{TYPE}", "Cases")}
                       data={props.config.data['cases']}
                       label={"cases"}
                       region={props.config.region}
                       showTopN={props.config.showTopN}/>
            </div>
            <div className={"right"}>
                <Panel dcidMap={props.config.dcidMap}
                       title={props.config.title.replace("{TYPE}", "Deaths")}
                       subtitle={props.config.subtitle.replace("{TYPE}", "Deaths")}
                       data={props.config.data['deaths']}
                       label={"deaths"}
                       region={props.config.region}
                       showTopN={props.config.showTopN}/>
            </div>
        </div>
    )
}
import React from "react";

export default function ToolTipContent(props: {chartInfo: string[], disclaimer: string}) {
    // Create a new line of h6 for every string in the array.
    let h6LabelInfo = props.chartInfo.map(text => <h5 className={"tooltip-content"}>{text}</h5>)

    return (
        <div style={{backgroundColor: 'white', padding: 10, borderRadius: 5}} className={"shadow"}>
            {h6LabelInfo}
            <div style={{margin: 10}}/>
            {props.disclaimer && <h5 className={"tooltip-content"}>{props.disclaimer}</h5>}
        </div>
    )
}
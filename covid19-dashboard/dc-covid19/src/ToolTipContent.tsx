import React from "react";

export default function ToolTipContent(props: {chartInfo: string[], disclaimer: string}) {
    // Create a new line of h6 for every string in the array.
    let h6LabelInfo = props.chartInfo.map(text =>
        <h6 className={"tooltip-content"}>{text}</h6>
    )

    return (
        <div style={{backgroundColor: 'white', padding: 10, borderRadius: 5}}>
            {h6LabelInfo}
            {props.disclaimer && <h6 className={"tooltip-content"}>{props.disclaimer}</h6>}
        </div>
    )
}
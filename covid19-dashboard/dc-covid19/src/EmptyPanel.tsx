import React from "react";

type Props = {
    reason: "loading" | "nan"
}
export default function(props: Props){
    let text: string = "Loading..."
    if (props.reason === 'nan') text = "No Data To Display"
    return (
        <div className={"panel chart shadow empty-panel"}>
            <h2 className={"empty-panel"}>{text}</h2>
        </div>
    )
}
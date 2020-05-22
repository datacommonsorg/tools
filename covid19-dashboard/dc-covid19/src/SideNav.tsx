import React from "react";
import SideNavText from "./SideNavText"

export default function SideNav(props: {handleScrollOnRef, selectedDate: string}) {
    // Create the sideNav links and break them up by section using a <br/>.
    let sideNavLinks = SideNavText().map( i => {
        let subsection = [...i].map(typeOfData => {
            let key = Object.keys(typeOfData)[0]
            let text = typeOfData[key]
            return <a id={key} key={key} onClick={props.handleScrollOnRef}>{text}</a>
        })
        return [...subsection, <br/>]
    })

    return (
        <div className="sidenav shadow panel">
            {sideNavLinks}
        </div>
    )
}
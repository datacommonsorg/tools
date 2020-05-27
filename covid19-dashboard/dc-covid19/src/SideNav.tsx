import React from "react";
import PanelInfo from './PanelInfo.json'

export default function SideNav(props: {handleScrollOnRef}) {
    // Create the sideNav links and break them up by section using a <br/>.
    let sideNavLinks = Object.keys(PanelInfo).map( key => {
        const text = PanelInfo[key].sideNavText;
        return <a id={key} key={key} onClick={props.handleScrollOnRef}>{text}</a>
    })

    return (
        <div className="sidenav shadow panel">
            {sideNavLinks}
        </div>
    )
}
import React from "react";

export default function SideNav(props: {handleScrollOnRef, date: string}) {
    return (
        <div className="sidenav shadow panel">
            <a id={"daily"} onClick={props.handleScrollOnRef}>Daily</a>
            <a id={"dailyPerCapita"} onClick={props.handleScrollOnRef}>Daily Per Capita</a>
            <a id={"dailyIncrease"} onClick={props.handleScrollOnRef}>Daily Increase</a>
            <br/>

            <a id={"weekly"} onClick={props.handleScrollOnRef}>Weekly</a>
            <a id={"weeklyPerCapita"} onClick={props.handleScrollOnRef}>Weekly Per Capita</a>
            <a id={"weeklyIncrease"} onClick={props.handleScrollOnRef}>Weekly Increase</a>
            <br/>


            { // 2 months ago there wasn't enough county COVID19 information, there is no point of showing options.
                props.date === "thirtyDays" || <a id={"monthly"} onClick={props.handleScrollOnRef}>Monthly</a>}
                {props.date === "thirtyDays" || <a id={"monthlyPerCapita"} onClick={props.handleScrollOnRef}>Monthly Per Capita</a>}
                {props.date === "thirtyDays" || <a id={"monthlyIncrease"} onClick={props.handleScrollOnRef}>Monthly Increase</a>}
            <br/>

            <a id={"absoluteCumulative"} onClick={props.handleScrollOnRef}>Cumulative</a>
            <a id={"cumulativePerCapita"} onClick={props.handleScrollOnRef}>Cumulative Per Capita</a>
        </div>
    )
}
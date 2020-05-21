import React from 'react';
import numberWithCommas from "./NumerWithCommas";
import {Bar, BarChart, LabelList, Tooltip, XAxis, YAxis} from 'recharts'

type dataHolder = {regionName: string, value: number, absolute: number, population: number, dcid: string, labelListLabel: string}
type Props = {data: dataHolder[], label: string, region: string, color: string, dcidMap: {}, show: number}
export default function Chart(props: Props) {
    /**
     * In charge of displaying the tooltip on-hover on the chart.
     *
     * @param active
     * @param payload
     * @param label
     */
    const customTooltip = ({active, payload, label}) => {
        // Make sure that the current bar is actively being hovered onl.
        if (active) {
            // If per-capita
            if (payload[0].payload.absolute && payload[0].payload.population) {
                return (
                    <div style={{backgroundColor: 'white', padding: 10, borderRadius: 5}}>
                        <h6 style={{
                            margin: 2,
                            fontWeight: "bold",
                            color: 'grey'
                        }}>{`${payload[0].payload.value} ${props.label} per 10,000 people`}</h6>
                        <h6 style={{
                            margin: 2,
                            fontWeight: "normal",
                            color: 'grey'
                        }}>{`New ${props.label}: ${numberWithCommas(payload[0].payload.absolute)}`}</h6>
                        <h6 style={{
                            margin: 2,
                            fontWeight: "normal",
                            color: 'grey'
                        }}>{`Total population: ${numberWithCommas(payload[0].payload.population)} people`}</h6>
                    </div>
                );
            // If percent increase
            } else if (payload[0].payload.absolute && !payload[0].payload.population) {
                return (
                    <div style={{backgroundColor: 'white', padding: 10, borderRadius: 5}}>
                        <h6 style={{margin: 2, textAlign: "center"}}>{payload[0].payload.label}</h6>
                        <h6 style={{
                            margin: 2,
                            fontWeight: "bold",
                            color: 'grey'
                        }}>{`Percent increase: ${numberWithCommas(payload[0].payload.value)}%`}</h6>
                        <h6 style={{margin: 2, fontWeight: "normal", color: 'grey'}}>Absolute
                            increase: {`${numberWithCommas(payload[0].payload.absolute)} ${props.label}`}</h6>
                    </div>)
            // Else, only display the absolute number
            } else {
                return (
                    <div style={{backgroundColor: 'white', padding: 10, borderRadius: 5}}>
                        <h6 style={{margin: 2, textAlign: "center"}}>{payload[0].payload.label}</h6>
                        <h6 style={{
                            margin: 2,
                            fontWeight: "bold",
                            color: 'grey'
                        }}>{`${numberWithCommas(payload[0].payload.value)} ${props.label}`}</h6>
                    </div>
                );
            }
        }
        return null;
    };

    /**
     * Function triggered when each bar in the cart is clicked.
     * Opens a new tab and takes the user to GNI.
     * @param e
     */
    let barOnClick = (e) => {
        let URL = `https://browser.datacommons.org/gni#&place=${e.dcid}&ptpv=MedicalConditionIncident,cumulativeCount,medicalStatus,ConfirmedOrProbableCase,incidentType,COVID_19__MedicalConditionIncident,cumulativeCount,medicalStatus,PatientDeceased,incidentType,COVID_19&pc=1`
        window.open(URL, '_blank');
    }


    /**
     * Function in charge of displaying the labeListLabel string stored in each dataHolder point.
     * @param metadata
     */
    let renderCustomizedLabel = (metadata) => {
        const {x, y, width, height, value} = metadata;
        return (
            <g>
                <text fontSize={9} x={x + width / 2} y={y + height / 2} fill="#fff" textAnchor="middle" dominantBaseline="middle">
                    {value}
                </text>
            </g>
        );
    };

    return (
        <BarChart
            width={400}
            height={35 * props.data.length}
            data={props.data}
            barSize={20}
            layout="vertical">
            <XAxis type="number" tick={{fill: '#868E96', fontSize: 12, fontWeight: 'bold'}}/>
            <YAxis type="category" dataKey="regionName" tick={{ill: '#868E96', fontSize: 10}} width={75}
                   interval={0} domain={[dataMin => (0 - Math.abs(dataMin)), dataMax => (dataMax * 2)]}/>
            <Tooltip content={customTooltip}/>
            <Bar dataKey={"value"} fill={props.color} onClick={barOnClick} radius={[3, 3, 3, 3]}
                 isAnimationActive={true}>
                <LabelList className={"labelList"}
                           dataKey={"labelListLabel"}
                           content={renderCustomizedLabel}/>
            </Bar>
        </BarChart>
    );
}
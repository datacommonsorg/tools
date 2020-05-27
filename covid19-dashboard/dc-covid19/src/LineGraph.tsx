/**
 Copyright 2020 Google LLC

 Licensed under the Apache License, Version 2.0 (the "License");
 you may not use this file except in compliance with the License.
 You may obtain a copy of the License at

 https://www.apache.org/licenses/LICENSE-2.0

 Unless required by applicable law or agreed to in writing, software
 distributed under the License is distributed on an "AS IS" BASIS,
 WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 See the License for the specific language governing permissions and
 limitations under the License.
 */
import React from 'react';
import {Bar, BarChart, LabelList, Line, LineChart, Tooltip, XAxis, YAxis} from 'recharts'

type Props = {
    data: any,
    label: string,
    region: string,
    dcidMap: {},
    selectedShowTopN: number
}
export default function LineGraph(props: Props) {
    const color: string = props.label === 'cases' ? '#990001' : 'grey'
    let data = props.data[0] || {}
    let lines: JSX.Element[] = []
    for (let x in data){
        if (x === 'label') continue
        lines.push(<Line type="monotone" dataKey={x} stroke={color} />)
    }
    return (
        <LineChart width={500}
                  height={500}
                  data={props.data}>
            <XAxis dataKey={"label"} />
            <YAxis tick={{ill: '#868E96', fontSize: 10}}
                   width={90}
                   interval={0}/>
            {lines}
        </LineChart>
    );
}

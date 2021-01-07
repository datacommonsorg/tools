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
import {Colors} from './Utils';
import numeral from 'numeral'

type CountPanelPropsType = {
  textToValue: {title: string; value: number; color?: string}[];
};
export default function CumulativePanel(props: CountPanelPropsType) {
  const totalRows = Object.keys(props.textToValue).length;
  const pctWidthPerRow = 100 / totalRows + '%';

  return (
    <div className={'panel count-panel'}>
      {props.textToValue.map((obj, index) => {
        const title = obj.title;

        // If value is nullish (including 0), display a dash.
        let value = "-"
        if (obj.value) {
          value = numeral(obj.value).format('0.0a')
        }

        const color = obj.color ? Colors(obj.color) : 'grey';
        return (
          <div className={'column'} key={index} style={{width: pctWidthPerRow}}>
            <h6 style={{color: color, fontWeight: 'bold'}}>{title}</h6>
            <h5 style={{color: color}}>{value}</h5>
          </div>
        );
      })}
    </div>
  );
}
import React from 'react';
import {numberWithCommas, Colors} from './Utils';

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
        const value = numberWithCommas(obj.value);
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

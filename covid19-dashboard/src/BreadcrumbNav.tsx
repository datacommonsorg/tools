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

import {Breadcrumb} from 'react-bootstrap';
import React from 'react';

type BreadcrumbNavPropsType = {
  items: {active: boolean; onClick: () => void; text: string}[];
};

/**
 *
 * @param props.active: is the button active?
 * @param props.onClick: what should happen when it's clicked
 * @param props.text: what is the text to display?
 * @constructor
 */
export default function BreadcrumbNav(props: BreadcrumbNavPropsType) {
  if (props.items.length <= 1) {
    return <></>;
  }
  return (
    <Breadcrumb className={'breadcrumb-mod'}>
      {props.items.map(item => {
        return (
          <Breadcrumb.Item href="#"
                           active={item.active}
                           onClick={item.onClick}>
            {item.text}
          </Breadcrumb.Item>
        );
      })}
    </Breadcrumb>
  );
}

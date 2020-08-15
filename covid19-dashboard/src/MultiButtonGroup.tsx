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
import Button from 'react-bootstrap/Button';
import ButtonGroup from 'react-bootstrap/ButtonGroup';

type MultiButtonGroup = {
  items: {active: boolean; onClick: () => void; text: string}[];
};

/**
 * Button group allowing the user to
 * @param props.items: the list of objects representing the buttons.
 */
export default (props: MultiButtonGroup) => {
  return (
    <ButtonGroup className={'button-group'}>
      {props.items.map((button, index) => {
        // If button is ON or OFF, the styling is different.
        // If the button is ON, use selected class to style the button.
        const buttonEnabledClass = button.active ? 'selected' : 'unselected';

        return (
          <Button
            className={buttonEnabledClass}
            key={index}
            onClick={button.onClick}
          >
            {button.text}
          </Button>
        );
      })}
    </ButtonGroup>
  );
};

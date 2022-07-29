/**
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *      http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import React, {Component} from 'react';
import {Series} from './back-end/data';

interface TimeGraphPropType {
    /** 
     * Passes the data to be plotted
     */
    data: Series[];
}

interface TimeGraphStateType {

}


/** Component to display a single graph */
class TimeGraph extends Component<TimeGraphPropType, TimeGraphStateType> {
    /** Constructor for class, sets initial state
    * @param {Object} props the props passed in by parent component
    */
    constructor(props: TimeGraphPropType) {
        super(props);
        this.state = {
        
        };
    }

    /** Renders the TimeGraph component.
     * @return {Object} the component using TSX code
     */
    render() {
        return (
            <div>hello</div>
        );
    }

}


export {TimeGraph};

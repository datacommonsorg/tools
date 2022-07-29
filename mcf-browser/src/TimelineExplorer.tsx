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

import React, { Component } from 'react';

import { Series } from './back-end/data';

interface TimelineExplorerPropType {
    /** 
     * Passes the data to be plotted
     */
    data: Series[];
}

interface TimelineExplorerStateType {

}


/** Component to display the timeline explorer */
class TimelineExplorer extends Component<TimelineExplorerPropType, TimelineExplorerStateType> {
    /** Constructor for class, sets initial state
    * @param {Object} props the props passed in by parent component
    */
    constructor(props: TimelineExplorerPropType) {
        super(props);
        this.state = {

        };
    }

    /** Renders the TimelineExplorer component.
     * @return {Object} the component using TSX code
     */
    render() {
        if(this.props.data.length === 0) {
            return null;
        }
        return (
            <div className="box">
                <h3>Timeline Explorer</h3>
                <ul>
                    {this.props.data.map((series) =>
                    <li key={series.id}>{series.id}</li>)}
                </ul>
            </div>
        );
    }
}


export { TimelineExplorer };

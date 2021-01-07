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

import './navigationbar.scss'
import React, {ChangeEvent} from "react";

type HeaderPropsType = {
  title: string,
  subtitle: string,
  onType: (event: ChangeEvent) => void
}

/**
 * The navigation header shown on top of the page.
 * @param props.title: the title of the page.
 * @param props.subtitle: the subtitle of the page.
 * @param props.onSearchInput: callback for when the user types on search bar.
 */
export default (props: HeaderPropsType) => (
  <header id="main-header">
    <nav className="navbar navbar-dark navbar-expand-lg col"
         id="main-nav">
      <div className="container-fluid">
        <div className="navbar-brand">
          <a href={"https://datacommons.org/"}>
            {props.title}
          </a>
          <span> {props.subtitle}</span>
        </div>
        <form className="form-inline">
          <a className="nav-link" href={"/dashboard/?dashboardId=covid19"}>COVID-19</a>
          <a className="nav-link" href={"/dashboard/?dashboardId=socialWellness"}>Social Wellness</a>
          <input className="form-control mr-sm ml-4"
                 type="text"
                 onKeyDown={
                   // Prevents re-load of page when on-enter.
                   (e) => {
                   if (e.keyCode === 13) e.preventDefault()
                 }}
                 onChange={props.onType}
                 placeholder={"Search for Place"}/>
        </form>
      </div>
    </nav>
  </header>
)
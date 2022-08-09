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

// the number of pages to display from the start and end initially
// 1, 2, ... NUM_PAGES_TO_DISPLAY
const NUM_PAGES_TO_DISPLAY = 3;

 interface PageBarPropType {
     /** Tracks which page the user is currently viewing (0-indexed) */
     page: number;

     /** Stores the maximum number of pages */
     maxPage: number;

     /** The function to go to the next page */
     onNextPageClicked: (page: number, maxPage: number) => void;

     /** The function to go to the previous page */
     onPrevPageClicked: (page: number) => void;

     /** The function to go to a certain page */
     onPageNumClicked: (page: number) => void;
 }

/** Component for rendering the pagination bar */
class PageBar extends Component<PageBarPropType> {
  /**
    * Returns the span to be used for a given page string
    * @param {string} pageString the string to display
    * @param {number} i the index of the page string
    * @return {JSX.Element} the span element in TSX code
    */
  renderPageBox(pageString: string, i: number) : JSX.Element {
    if (pageString === '...') {
      // return non-clickable span
      return <span className="ellipses-box" key={i}>{pageString}</span>;
    } else {
      return (
        <span
          className={
             (this.props.page + 1).toString() === pageString ?
             'page-box curr-page-box':
             'page-box'
          }
          key={i}
          onClick={() => this.props.onPageNumClicked(parseFloat(pageString))}
        >
          {pageString}
        </span>
      );
    }
  }

  /** Get page strings given the current page
    * @param {number} page the current page that the user is on
    * @return {string[]} the strings to render in the pagination bar
    */
  getPageStrings(page: number) : string[] {
    // Get all page strings
    const actualPage = page + 1; // Switch from 0-indexed to 1-indexed
    const maxPage = this.props.maxPage;
    let pagesToDisplay: Set<number>;

    // Check if page is on the boundary
    if (
      actualPage < NUM_PAGES_TO_DISPLAY ||
        actualPage > maxPage - NUM_PAGES_TO_DISPLAY + 1
    ) {
      // Generate pages to display
      const pagesList = [];

      for (let i = 0; i < NUM_PAGES_TO_DISPLAY; i++) {
        pagesList.push(i + 1);
        pagesList.push(maxPage - i);
      }

      // Filter out duplicates and out of bounds
      pagesToDisplay = new Set(
          pagesList.filter((i) => i > 0 && i <= maxPage),
      );
    } else {
      const pagesList =
         [1, actualPage - 1, actualPage, actualPage + 1, maxPage];
      pagesToDisplay = new Set(pagesList);
    }

    const pages = [...pagesToDisplay];
    pages.sort((a, b) => a - b);

    const pageStrings = [];
    let prevPage = null;
    for (const i of pages) {
      if (prevPage && (i - prevPage) > 1) {
        pageStrings.push('...');
      }
      pageStrings.push(i.toString());
      prevPage = i;
    }

    return pageStrings;
  }

  /** Returns previous page
    * @param {number} currPage the current page the user is on
    * @return {number} the previous page
    */
  static getPrevPage(currPage: number) : number {
    return (currPage === 0) ? 0 : currPage - 1;
  }

  /** Return next page
    * @param {number} currPage the current page the user is on
    * @param {number} maxPage the maximum number of pages
    * @return {number} the next page
    */
  static getNextPage(currPage: number, maxPage: number) : number {
    return (currPage === maxPage - 1) ? maxPage - 1 : currPage + 1;
  }


  /**
    * Renders the bar that allows user to control the page
    * @return {JSX.Element} the component in TSX code
    */
  render() : JSX.Element {
    // Get all page strings
    const pageStrings = this.getPageStrings(this.props.page);

    // Render all page strings
    return (
      <div className="page-bar">
        <span
          className="page-box"
          onClick={() => this.props.onPrevPageClicked(this.props.page)}
        >← prev</span>
        {
          pageStrings.map((page, i) => this.renderPageBox(page, i))
        }
        <span
          className={'page-box'}
          onClick={() => this.props.onNextPageClicked(
              this.props.page,
              this.props.maxPage,
          )}
        >next →</span>
      </div>
    );
  }
}

export {PageBar};

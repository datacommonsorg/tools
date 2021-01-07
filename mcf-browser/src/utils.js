/**
 * Copyright 2020 Google LLC
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

/* Simple component to render the colors legend. */
const colorLegend = {
  'exist-in-kg': 'Node has dcid that exists in DC KG',
  'exist-in-local': 'Node has resolved local reference and no dcid',
  'not-in-local': 'Node has unresolved local reference and no dcid',
  'not-in-kg': 'Node has dcid which does not exist in DC KG',
};

/**
 * Sets the window hash value to query a given id.
 *
 * @param {string} homeHash The hash saveed in App's state, preserving file
 *     names within url.
 * @param {string} id The id of the desired node to display. This can be either
 *     a dcid or a local id.
 */
function goToId(homeHash, id) {
  if (id.includes(':')) {
    window.location.hash = homeHash + '&id=' + id;
  } else {
    window.location.hash = homeHash + '&id=dcid:' + id;
  }
}

/**
 * Sets the window hash value to query a given id.
 * @param {string} homeHash The hash saveed in App's state, preserving file
 *     names within url.
 * @param {string} id The id of the desired node to display. This can be either
 *     a dcid or a local id.
 */
function searchId(homeHash, id) {
  if (id.includes(':')) {
    window.location.hash = homeHash + '&search=' + id;
  } else {
    window.location.hash = homeHash + '&search=dcid:' + id;
  }
}

/**
 * Sets the window hash value to given value.
 * @param {string} hash The value that the window's hash should be set to.
 */
function goTo(hash) {
  window.location.hash = hash;
}

/**
 * Opens the given file url.
 * @param {String} fileUrl Url of the fileee to open.
 */
function openFile(fileUrl) {
  if (fileUrl.startsWith('https')) {
    window.open(fileUrl);
  }
}


export {colorLegend, goToId, goTo, openFile, searchId};

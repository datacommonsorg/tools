# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import six.moves.urllib.error
import six.moves.urllib.request
import json
import zlib
import base64


def send_request(req_url, req_json={}, compress=False, post=True):
    """ Sends a POST/GET request to req_url with req_json, default to POST.
    Returns:
    The payload returned by sending the POST/GET request formatted as a dict.
    """
    # Get the API key
    headers = {
        'Content-Type': 'application/json'
    }

    # Send the request and verify the request succeeded
    if post:
        req = six.moves.urllib.request.Request(req_url, data=json.dumps(req_json).encode('utf-8'), headers=headers)
    else:
        req = six.moves.urllib.request.Request(req_url, headers=headers)

    try:
        res = six.moves.urllib.request.urlopen(req)
    except six.moves.urllib.error.HTTPError as e:
        raise ValueError(
            'Response error: An HTTP {} code was returned by the mixer. Printing '
            'response\n\n{}'.format(e.code, e.read()))

    # Get the JSON
    res_json = json.loads(res.read())
    if 'payload' not in res_json:
        raise ValueError('Response error: Payload not found. Printing response\n\n''{}'.format(res.text))

    # If the payload is compressed, decompress and decode it
    payload = res_json['payload']
    if compress:
        payload = zlib.decompress(base64.b64decode(payload), zlib.MAX_WBITS | 32)
    return json.loads(payload)

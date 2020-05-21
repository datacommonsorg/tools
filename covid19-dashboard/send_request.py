import os
import six.moves.urllib.error
import six.moves.urllib.request
import json
import zlib
import base64

_ENV_VAR_API_KEY = "AIzaSyCNCHj4uelGpDzcnU-o2cZD44Hs9J78n8I"


def send_request(req_url, req_json={}, compress=False, post=True):
    """ Sends a POST/GET request to req_url with req_json, default to POST.
    Returns:
    The payload returned by sending the POST/GET request formatted as a dict.
    """
    # Get the API key
    headers = {
        'x-api-key': _ENV_VAR_API_KEY,
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

# Copyright 2020 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import collections
import csv
import requests


sparql = '''
SELECT ?dcid ?name ?parent ?type
WHERE {
	?a typeOf Place .
	?a name ?name .
	?a containedInPlace ?parent .
	?a dcid ?dcid .
	?a subType ?type .
	?parent typeOf County .
}
'''


response = requests.post(
  'https://api.datacommons.org/query', json={'sparql': sparql})
res_json = response.json()


# Parent -> [child] mapping
tree = collections.defaultdict(list)
for row in  res_json['rows']:
		ptype = row['cells'][3].get('value', '')
		if ptype == "CensusTract":
			continue
		parent = row['cells'][2].get('value', '')
		tree[parent].append(
      [row['cells'][1].get('value',''), row['cells'][0].get('value', '')])


with open('result.csv', mode='w') as csv_file:
    csv_writer = csv.writer(csv_file, delimiter=',')
    for parent, children in tree.items():
        # Sort the children by name.
        children.sort(key=lambda place: place[0])
        current = []
        token = "."
        first = True
        for c in children:
            parts = c[0].split(" ")
            # This is the similarity check, can expand this to handle more cases.
            if parts[0] == token:
                if first:
                    csv_writer.writerow(current)
                csv_writer.writerow(c)
                first = False
            else:
                current = c
                token = parts[0]
                first = True
# Copyright 2021 Google LLC
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


# Generate py protobuf:
# protoc -I=./ --python_out=./ ./stat_config.proto

from google.protobuf import text_format
import stat_config_pb2
import logging
import sys
import collections

import util


logging.basicConfig(stream=sys.stdout, level=logging.INFO)


def analyze(prop_list, pt_to_info_list, existing_keys):
    props = prop_list.props

    result = []
    for pt_mprop, info_list in pt_to_info_list.items():
        pt, mprop = pt_mprop.split("^")
        pv_mapping = {}
        is_dpv_case = False
        for prop in props:
            curr_set = set()
            for info in info_list:
                curr_set.add(info.pv[prop])
            if len(curr_set) == 1:
                is_dpv_case = True
            pv_mapping[prop] = curr_set

        if is_dpv_case:
            spec = stat_config_pb2.PopObsSpec(pop_type=pt)
            spec.obs_props.append(stat_config_pb2.ObsProp(mprop=mprop))
            valid = True
            for p, vset in pv_mapping.items():
                if len(vset) == 1:
                    v = next(iter(vset))
                    if p == "householdType" and v == "Houseless":
                        valid = False
                        break
                    spec.dpv.append(stat_config_pb2.PopObsSpec.PV(prop=p, val=v))
                else:
                    spec.cprop.append(p)
            if not valid:
                continue
            keys = util.compute_pop_obs_spec_keys(spec)
            for key in keys:
                if key not in existing_keys:
                    # print(key)
                    result.append(spec)
    return result



def run():
    spec_list = []
    existing_keys = util.get_existing_dpv_spec_key()
    for key in existing_keys:
        print(key)
    data = util.read_data()
    prop_list_2_stat_var = collections.defaultdict(lambda: collections.defaultdict(list))
    for id, info in data.items():
        prop_list = util.PropList(info.pv.keys())
        prop_list_2_stat_var[prop_list][info.pt + "^" + info.mprop].append(info)
    all_prop_list =  sorted(list(prop_list_2_stat_var.keys()))
    for prop_list in all_prop_list:
        specs = analyze(prop_list, prop_list_2_stat_var[prop_list], existing_keys)
        spec_list.extend(specs)

    result = stat_config_pb2.PopObsSpecList(spec=spec_list)
    f = open("dpv.textproto", "w")
    f.write(text_format.MessageToString(result))
    f.close()

if __name__ == '__main__':
    run()
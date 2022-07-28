
import csv
from google.protobuf import text_format
import stat_config_pb2


class QueryData():
    def __init__(self, pt, pv, mprop):
        self.pt = pt
        self.pv = pv
        self.mprop = mprop


class PropList(object):
    def __init__(self, props=[]):
        self.props = sorted(props)
    def __eq__(self, other):
        return hasattr(other, 'props') and self.props == other.props
    def __lt__(self,other):
        if len(self.props) == len(other.props):
            for i in range(len(self.props)):
                if self.props[i] != other.props[i]:
                    return self.props[i] < other.props[i]
        return len(self.props) < len(other.props)
    def __hash__(self):
       return hash(''.join(self.props))


def read_pop_obs_spec(file_path):
    """Read pop obs spec from the config file."""
    # Read pop_obs_specs with multiple obs_props
    pop_obs_spec_list = stat_config_pb2.PopObsSpecList()
    with open(file_path, 'r') as file_common:
        data_common = file_common.read()
    text_format.Parse(data_common, pop_obs_spec_list)
    return pop_obs_spec_list


def compute_pop_obs_spec_keys(spec):
    pt = spec.pop_type
    result = set()
    for obs_prop in spec.obs_props:
        mprop = obs_prop.mprop
        key = '{},{},{}'.format(pt, mprop, ','.join(sorted(spec.cprop)))
        dpv = {x.prop: x.val for x in spec.dpv}
        for dp in sorted(list(dpv.keys())):
            key += '|{}-{}'.format(dp, dpv[dp])
            result.add(key)
    return result


def get_existing_dpv_spec_key():
    pop_obs_spec_list = read_pop_obs_spec("./pop_obs_spec_common.textproto")
    result = set()
    for spec in pop_obs_spec_list.spec:
        if len(spec.dpv) == 0:
            continue
        result = result.union(compute_pop_obs_spec_keys(spec))
    return result


def read_data():
    with open('statvar.csv') as csvfile:
        csvreader = csv.reader(csvfile, delimiter=',')
        next(csvreader)
        data = {}
        for row in csvreader:
          id = row[0]
          pt = row[2]
          mprop = row[3]
          stat_type = row[4]
          if mprop.startswith("eia") or stat_type == "marginOfError":
              continue
          pv = {}
          for i in range(0, 6):
            ind = i*2+8
            # Filter
            if row[ind]:
              pv[row[ind]] = row[ind+1]
          data[id] = QueryData(pt, pv, mprop)
    return data

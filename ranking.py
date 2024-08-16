# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https:#www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datacommons as dc
import json
import urllib
import sys
import threading
import os.path

threadedp = False

US_dcid = "country/USA"

statVarConfig = None
allStatVars = []
def readVars (file):
    f = open(file)
    jsstr = f.read()
    f.close()
    statVarConfig = json.loads(jsstr)
    for svc in statVarConfig:
        for sv in svc["statsVars"]:
            if (sv not in allStatVars):
                allStatVars.append(sv)
            if ("relatedChart" in svc and "denominator" in svc["relatedChart"]):
                denom = svc["relatedChart"]["denominator"]
                if (denom not in allStatVars):
                    allStatVars.append(denom)

    print("%s stat vars" % (len(allStatVars)))

readVars("../website/server/chart_config.json")

def loadDataFromDC (statsFile):
    items = RankStatVarPlace.pendingItems
    start = 0
    inc = 100

    while (start < len(items)) :
        if (start + inc < len(items)):
            next = items[start:start+inc]
        else :
            next = items[start:]
        if (threadedp) :
            th = threading.Thread(target=getSVInThread, args=[next])
        else:
            getSVInThread(next)
        start = start + inc


    def getSV ():
        items = RankStatVarPlace.pendingItems.copy()
        getSVInThread(items)
        #th = threading.Thread(target=getSVInThread, args=[items])
        RankStatVarPlace.pendingItems = []
     #   th.start()
        
        
def getSVInThread (items):
    childIds = []
    for ch in items:
        childIds.append(ch.dcid)
        # this can be made much faster ...
    vals = dc.get_stat_all(childIds, allStatVars)
    for pl in items:
        for statVar in allStatVars:
            try :
                plvals = vals[pl.dcid]
                svals = plvals[statVar]
                (val, date) = getLatest(svals)
                pl.statVars[statVar] = val
           #     print("%s %s %s %s" % (pl.dcid, statVar, val, date))
            except ValueError:
                continue
            except KeyError:
                continue
        print("%s %i" % (pl.dcid, len(pl.statVars)))

def getLatest(sval) :
    date = 0
    val = None
    for series in sval['sourceSeries']:
        for key in series['val'].keys():
            dd = int(key)
            if (dd > date) :
                date = dd
                val = series['val'][key]
    return (val, date)


class RankStatVarPlace:

    idPlaceMap = {}
    pendingItems = []

    @staticmethod
    def getPlace (type, dcid) :
        if (dcid in RankStatVarPlace.idPlaceMap):
            return RankStatVarPlace.idPlaceMap[dcid]
        else :
            return RankStatVarPlace(type, dcid)
        
    def __init__ (self, type, dcid) :
        self.dcid = dcid
        self.type = type
        self.children = []
        self.statVars = {}
        RankStatVarPlace.idPlaceMap[dcid] = self
        if ('wiki' not in dcid and self not in RankStatVarPlace.pendingItems):
            RankStatVarPlace.pendingItems.append(self)

    def addChild (self, child) :
        self.children.append(child)

        
    
            
def buildPlaceTree (placeFile):
    if (os.path.isfile(placeFile)):
        ff = open(placeFile)
        for line in ff:
            it = line.strip().split('\t')
            pl = RankStatVarPlace.getPlace(it[1], it[0])
            par = RankStatVarPlace.getPlace(it[3], it[2])
            par.addChild(pl)
    else :
        US = RankStatVarPlace.getPlace("Country", US_dcid)
        states = dc.get_places_in([US_dcid], "State")[US_dcid]
        for state in states:
            st = buildPlaceTreeState(state)
            US.addChild(st)
        ff = open(placeFile, "w")
        for c in US.children:
            dumpPlaces(ff, c, US)
        ff.close()

def dumpPlaces (ff, node, parent) :
    str = "%s\t%s\t%s\t%s\n" % (node.dcid, node.type, parent.dcid, parent.type)
    ff.write(str)
    for it in node.children:
        dumpPlaces(ff, it, node)

def buildPlaceTreeState(state):
    st = RankStatVarPlace.getPlace("State", state)
    counties = dc.get_places_in([state], "County")[state]
    for county in counties:
        cnt = RankStatVarPlace.getPlace("County", county)
        st.addChild(cnt)
        cities = dc.get_places_in([county], "City")[county]
        for city in cities:
            ct = RankStatVarPlace.getPlace("City", city)
            cnt.addChild(ct)
    return st



def dumpStatsInt (f, node):
    str = node.dcid +"\t" + node.type
    if (len(node.statVars) > 0):
        for stat in allStatVars:
            if (stat in node.statVars):
                str = str + "\t" + "%i" % (node.statVars[stat])
            else :
                str = str + "\t" + " "
        f.write(str + "\n")
    for child in node.children:
        dumpStatsInt(f, child)

def dumpStats (file):
    f = open(file, "w")
    str = "dcid\ttype"
    for stat in allStatVars:
        str = str + "\t" + stat
    f.write(str + "\n")
    US = RankStatVarPlace.getPlace("Country", US_dcid)
    for c in US.children:
        dumpStatsInt(f, c)
    f.close()

def loadDataFromFile (statsFile):
    f = open(statsFile)
    varLine = f.readLine()
    vars = varLine.strip().split('\t')
    for line in f:
        vals = line.strip().split('\t')
        dcid = vals[0]
        type = vals[1]
        node = RankStatVarPlace.getPlace(type, dcid)
        node.vars = {}
        i = 2
        while (i < len(vars)):
            node.vars[vars[i]] = vals[i]
            i = i + 1
                   
    
def loadStats (statsFile, reloadp) :
    if ((not os.path.isfile(statsFile)) or reloadp) :
        loadDataFromDC(statsFile)
        if (len(statsFile) > 0):
            dumpStats(statsFile)
    else:
        loadDataFromFile(statsFile)
    

buildPlaceTree("places.txt")
print("Finished Building Place Tree")
#loadStats("fullStats.tsv", 1)
loadStats("", 1)

#!/usr/bin/env python3
"""Summarize collector JSONL without assigning unknown hardware semantics.
IDLE percentages normalize by each channel's complete residency sum.
Mean residence per reported entry is an interval aggregate, not wake latency.
"""
import sys,json,collections,pathlib

def summarize(path):
    rows=[json.loads(line) for line in open(path) if line.strip()]
    deltas=[r for r in rows if r['type']=='delta']
    agg={}
    elapsed=sum(r['elapsed_s'] for r in deltas)
    for r in deltas:
        for c in r['channels']:
            key=(c['group'],c['subgroup'],c['name'],c['driver_id'],c['channel_id'])
            if key not in agg:
                agg[key]={k:v for k,v in c.items() if k not in ['states','value','raw']}
                agg[key]['states']={}
                agg[key]['value']=0
            a=agg[key]
            if 'value' in c:
                if c['value']==-(1<<63):a['invalid']=True
                else:a['value']+=c['value']
            for s in c.get('states',[]):
                x=a['states'].setdefault(s['name'],{'residency':0,'intransitions':0})
                x['residency']+=s['residency'];x['intransitions']+=s['intransitions']
    out={'file':str(path),'intervals':len(deltas),'elapsed_s':elapsed,'first_date':deltas[0]['date'] if deltas else None,'last_date':deltas[-1]['date'] if deltas else None,'channels':[]}
    for a in agg.values():
        states=a['states'];total=sum(s['residency'] for s in states.values())
        if states:
            del a['value'];a['total_residency']=total
            for s in states.values():
                s['percentage']=100*s['residency']/total if total else None
                if a['unit'] in ['24Mticks','us','ns']:
                    factor={'24Mticks':1/24000000,'us':1e-6,'ns':1e-9}[a['unit']]
                    s['seconds']=s['residency']*factor
                    s['aggregate_us_per_entry']=s['seconds']*1e6/s['intransitions'] if s['intransitions'] else None
        else:del a['states']
        if a['unit']=='mJ' and a.get('value') is not None and elapsed and not a.get('invalid'):
            a['modeled_average_watts']=a['value']/1000/elapsed
        out['channels'].append(a)
    return out

if __name__=='__main__':
    for path in sys.argv[1:]:print(json.dumps(summarize(path),sort_keys=True))

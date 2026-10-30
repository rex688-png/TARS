"""Exact utterance allowlist, not an acoustic-confidence estimator."""
import re

ORDERS = {
    'fighter attack my target': ('npcOrder', {'orders':['FocusTarget']}, 'npcOrder', 'fighter_attack'),
    'fighter defend me': ('npcOrder', {'orders':['DefensiveBehaviour']}, 'npcOrder', 'fighter_defend'),
    'fighter return': ('npcOrder', {'orders':['ReturnToShip']}, 'npcOrder', 'fighter_return'),
    'launch the fighter': ('npcOrder', {'orders':['LaunchFighter1']}, 'npcOrder', 'fighter_launch'),
    'target power plant': ('targetSubmodule', {'subsystem':'Power Plant'}, 'targetSubmodule', 'subsystem'),
    'target drives': ('targetSubmodule', {'subsystem':'Drive'}, 'targetSubmodule', 'subsystem'),
    'four pips to systems': ('managePowerDistribution', {'power_category':['Systems'], 'pips':[4]}, 'managePowerDistribution', 'pips'),
    'balance power': ('managePowerDistribution', {'balance_power':True}, 'managePowerDistribution', 'balance'),
    'deploy heat sink': ('deployHeatSink', {}, 'deployHeatSink', 'heat_sink'),
}


def parse_order(text):
    if not isinstance(text,str) or len(text)>100:
        return None
    normalized = ' '.join(text.casefold().strip().rstrip('.!').split())
    normalized = re.sub(r'^fighter,\s*','fighter ',normalized)
    value = ORDERS.get(normalized)
    if value is None:
        return None
    # Do not expose shared mutable argument dictionaries to callers.
    import copy
    name,args,permission,kind = value
    return dict(name=name,args=copy.deepcopy(args),permission=permission,kind=kind)

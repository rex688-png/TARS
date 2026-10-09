"""One-shot UI approvals at the existing action dispatch boundary."""
import copy
import secrets
import threading
import time

RISKY = {'textMessage', 'fireWeapons', 'fireWeaponsBuggy', 'ejectAllCargo', 'ejectAllCargoBuggy'}

def permission_mode(config, key):
    if config.get('allowed_actions', {}).get(key) is False:
        return 'block'
    value = config.get('action_permissions', {}).get(key)
    return value if value in ('allow', 'ask', 'block') else ('ask' if key in RISKY else 'allow')

class ActionApprovals:
    def __init__(self, config, emit, clock=time.monotonic):
        self.config, self.emit, self.clock = config, emit, clock
        self.pending = {}
        self.lock = threading.Lock()

    def request(self, call, key):
        with self.lock:
            self.pending = {k:v for k,v in self.pending.items() if v[0] > self.clock()}
            if len(self.pending) >= 8:
                return 'Not executed: too many pending approvals.'
            token = secrets.token_urlsafe(24)
            self.pending[token] = (self.clock()+60, copy.deepcopy(call), key)
        self.emit('action_approval', request_id=token, action=call.function.name,
                  arguments=call.function.arguments, expires_in=60)
        return 'Not executed: awaiting explicit approval in TARS (expires in 60 seconds).'

    def resolve(self, token, approved):
        if not isinstance(token, str):
            return None
        with self.lock:
            entry = self.pending.pop(token, None)
        self.emit('action_approval_closed', request_id=token)
        if not entry or not approved or entry[0] <= self.clock():
            return None
        if permission_mode(self.config(), entry[2]) == 'block':
            return None
        return entry[1]

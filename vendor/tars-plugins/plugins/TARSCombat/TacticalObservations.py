"""Two conservative historical observations. No models, threads or controls."""
from .CombatState import stamp, number


class TacticalObservations:
    COOLDOWN = 120.0
    TTL = 4.0

    def __init__(self):
        self.scope = None
        self.last_attempt = float('-inf')
        self.reset(None)

    def reset(self, scope):
        self.scope = scope
        self.used = False
        self.pending = None
        self.target_key = None
        self.target_since = self.target_at = None
        self.shield = None
        self.recoveries = 0
        self.down_since = None
        self.last_hull = None
        self.hits = 0
        self.hull_at = float('-inf')
        self.status_at = float('-inf')
        self.main_shields_down = False
        self.quiet_until = 0

    def _target_clear(self):
        self.target_key = self.target_since = self.target_at = self.shield = None
        self.recoveries = 0
        if self.pending and self.pending['code']=='target_shield_recoveries': self.pending=None

    def update(self, data, now, tracker):
        scope = tracker.encounter['sequence'] if tracker.phase=='active' and tracker.encounter else None
        if scope != self.scope: self.reset(scope)
        if scope is None: return None
        at=stamp(data.get('timestamp'))
        if at is None or not 0<=now-at<=3: return None
        name=data.get('event')
        if name in ('Bounty','Loadout','VehicleSwitch','RepairAll'):
            self._target_clear();self.pending=None;self.quiet_until=now+10
            if name!='Bounty':
                self.down_since=None;self.hits=0;self.last_hull=None;self.main_shields_down=False
        if name=='ShipTargeted':
            key=(data.get('Ship'),data.get('PilotName'))
            if (data.get('TargetLocked') is not True or type(data.get('ScanStage')) is not int or
                data['ScanStage']<3 or not all(isinstance(k,str) and k for k in key) or
                not number(data.get('ShieldHealth'),0,100) or not number(data.get('HullHealth'),0,100)):
                self._target_clear()
            else:
                if key!=self.target_key or self.target_at is None or at-self.target_at>10:
                    self._target_clear();self.target_key=key;self.target_since=at
                value=data['ShieldHealth']
                if self.shield==0 and value>=20:self.recoveries+=1
                self.shield=value;self.target_at=at
        if name=='Status':
            flags=data.get('flags',{})
            self.main_shields_down=(isinstance(flags,dict) and flags.get('InMainShip') is True and flags.get('ShieldsUp') is False)
            if self.main_shields_down and (self.down_since is None or at-self.status_at>5):
                self.down_since=at;self.hits=0;self.last_hull=None
            self.status_at=at
            if not self.main_shields_down:
                self.down_since=None;self.hits=0;self.last_hull=None
        if name=='ShieldState' and tracker.vehicle=='mothership':
            if data.get('ShieldsUp') is False and self.down_since is None:
                self.down_since=at;self.hits=0;self.last_hull=None
            elif data.get('ShieldsUp') is True:
                self.down_since=None;self.hits=0;self.last_hull=None
        if name=='HullDamage' and data.get('Fighter') is False and number(data.get('Health'),0,1):
            if self.down_since is not None and at>=self.down_since:
                if self.last_hull is not None and data['Health']<self.last_hull:self.hits+=1
                self.last_hull=data['Health'];self.hull_at=at
        if self.used or now-self.last_attempt<self.COOLDOWN or now<self.quiet_until:return None
        if tracker.alerts or any(now-at<15 for at in tracker.last_alert.values()):return None
        if self._damage_valid(now,tracker):
            code='sustained_unshielded_damage'
            text="We're still taking hull damage after half a minute unshielded."
        elif self._target_valid(now,tracker) and now-self.target_since>=45:
            code='target_shield_recoveries'
            text="We've seen that target's shields recover at least twice."
        else:return None
        self.used=True;self.last_attempt=now
        self.pending=dict(code=code,text=text,created=now,expires=now+self.TTL,scope=scope,target=self.target_key)
        return self.pending

    def _damage_valid(self,now,tracker):
        return (tracker.vehicle=='mothership' and self.down_since is not None and
                now-self.down_since>=30 and self.main_shields_down and now-self.status_at<=5 and
                self.hits>=2 and now-self.hull_at<=5 and self.last_hull is not None and self.last_hull>.5 and
                tracker.mothership.get('shields_up') is False and tracker.mothership.get('hull',0)>.5)

    def _target_valid(self,now,tracker):
        target=tracker.target or {}
        return (self.target_key is not None and self.target_at is not None and now-self.target_at<=5 and
                self.recoveries>=2 and self.shield is not None and self.shield>=20 and
                number(target.get('HullHealth'),0,100) and target['HullHealth']>0 and
                number(target.get('ShieldHealth'),0,100) and target['ShieldHealth']>=20 and
                type(target.get('ScanStage')) is int and target['ScanStage']>=3 and now-target.get('at',float('-inf'))<=5 and
                (target.get('Ship'),target.get('PilotName'))==self.target_key)

    def text(self,data,now,tracker,*,started=False):
        candidate=self.pending
        if not candidate or tracker.phase!='active' or tracker.encounter is None:return None
        if ((data.get('code'),data.get('created'))!=(candidate['code'],candidate['created']) or
            (not started and now>=candidate['expires']) or tracker.encounter['sequence']!=candidate['scope'] or
            tracker.alerts or any(now-at<15 for at in tracker.last_alert.values())):return None
        if candidate['code']=='sustained_unshielded_damage':
            valid=self._damage_valid(now,tracker)
        else:valid=self.target_key==candidate['target'] and self._target_valid(now,tracker)
        return candidate['text'] if valid else None

"""Evidence-only combat tracker. Times are UTC epoch seconds supplied by caller.

A focus interval is not a kill or an individual fight. No game controls or speech
live here. Raw event data stays in memory; bounded records are session-local.
"""
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math


def stamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.replace(tzinfo=parsed.tzinfo or timezone.utc).timestamp()
    except (AttributeError, ValueError, TypeError):
        return None


def number(value, low=0, high=float('inf')):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and low <= value <= high


class CombatTracker:
    QUIET = 12.0
    THREAT_TTL = 20.0
    RECOVERY = 15.0
    TARGET_TTL = 15.0

    def __init__(self):
        self.phase = 'idle'
        self.music = False
        self.music_at = float('-inf')
        self.last_live_at = float('-inf')
        self.own_ship_key = None
        self.threat_at = float('-inf')
        self.danger = False
        self.status_at = float('-inf')
        self.quiet_since = None
        self.recovery_until = 0
        self.vehicle = 'unknown'
        self.shield_journal = None
        self.mothership = {}
        self.fighters = {}
        self.target = None
        self.encounter = None
        self.records = deque(maxlen=50)
        self.totals = dict(bounty_awards=0, bounty_credits=0, fighter_launches=0,
                           fighter_losses=0, fighter_rebuilds=0, shield_losses=0, hull_milestones=0, unknown_bounty_awards=0)
        self.sequence = 0
        self.scope_since = float("-inf")
        self.ship_id = None
        self.seen = {}
        self.watermarks = {}
        self.last_alert = {}
        self.alerts = []

    def _record(self, name, at, **fields):
        if self.encounter is not None:
            self.encounter['transitions'].append(dict(kind=name, at=at, **fields))
            self.encounter['transitions'] = self.encounter['transitions'][-200:]

    def _start(self, at, reason):
        if self.phase != 'active':
            self.sequence += 1
            self.encounter = dict(sequence=self.sequence, start=at, end=None, evidence=reason,
                                  targets={}, transitions=[], **{k: 0 for k in self.totals})
            self.phase = 'active'
            self.quiet_since = None
            self._record('focus_entered', at, reason=reason)

    def _count(self, key, amount=1):
        self.totals[key] += amount
        if self.encounter is not None:
            self.encounter[key] += amount

    def _end(self, at, reason):
        if self.encounter is not None:
            self._record('focus_exited', at, reason=reason)
            self.encounter['end'] = at
            self.records.append(self.encounter)
            self.encounter = None
        self.phase = 'recovering'
        self.recovery_until = at + self.RECOVERY
        self.quiet_since = None

    def tick(self, now):
        threat = (self.music or
                  now - self.threat_at <= self.THREAT_TTL or
                  self.danger and now - self.status_at <= 15)
        if self.phase == 'active' and not threat:
            if self.quiet_since is None:
                self.quiet_since = now
            elif now - self.quiet_since >= self.QUIET:
                self._end(now, 'quiet_hysteresis')
        elif threat:
            self.quiet_since = None
        if self.phase == 'recovering' and now >= self.recovery_until:
            self.phase = 'idle'
        self.alerts = [a for a in self.alerts if a['expires'] > now and self.alert_valid(a, now)]

    def _alert(self, code, text, at, **context):
        if at - self.last_alert.get(code, float('-inf')) < 30:
            return
        self.last_alert[code] = at
        self.alerts.append(dict(code=code, text=text, created=at, expires=at+5, **context))

    def alert_valid(self, alert, now):
        if now >= alert['expires'] or self.phase != 'active':
            return False
        code = alert['code']
        if code == 'shield_loss':
            return self.mothership.get('shields_up') is False
        if code == 'hull_critical':
            return self.mothership.get('hull', 1) <= .5
        if code == 'heat_danger':
            return self.mothership.get('overheating') is True
        fighter = self.fighters.get(alert.get('fighter_id'), {})
        return fighter.get('status') == ('destroyed' if code == 'fighter_destroyed' else 'ready')

    def consume(self, data, now, historic=False):
        if historic or not isinstance(data, dict):
            return False
        at = stamp(data.get('timestamp'))
        # Missing/future/stale events cannot enter live combat or create alerts.
        if at is None or not -2 <= now - at <= 30:
            return False
        if at < self.scope_since:
            return False
        name = data.get('event')
        channel = ('target' if name == 'ShipTargeted' else 'fighter:' + str(data.get('ID'))
                   if name in ('LaunchFighter', 'DockFighter', 'FighterDestroyed', 'FighterRebuilt') else
                   'hull:' + str(data.get('Fighter')) if name == 'HullDamage' else str(name))
        if at < self.watermarks.get(channel, float('-inf')):
            return False
        signature = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
        if signature in self.seen:
            return False
        self.seen[signature] = True
        while len(self.seen) > 2048:
            self.seen.pop(next(iter(self.seen)))
        self.watermarks[channel] = at
        self.last_live_at = max(self.last_live_at, at)
        self.tick(now)
        if name in ('LoadGame', 'Shutdown', 'Died', 'FSDJump', 'SupercruiseEntry', 'Docked'):
            self.scope_since = at
            if self.phase == 'active':
                self._end(at, name)
            self.music = self.danger = False
            self.threat_at = float('-inf')
            self.target = None
            self.alerts.clear()
            self.vehicle = 'mothership' if name in ('SupercruiseEntry','FSDJump','Docked') else 'unknown'
            if name in ('LoadGame', 'Died', 'FSDJump'):
                self.mothership = {}
                self.shield_journal = None
                self.fighters.clear()
                self.own_ship_key = None
                self.ship_id = None
            return True
        if name == 'Music':
            self.music = str(data.get('MusicTrack', '')).casefold().startswith('combat')
            self.music_at = at
            if self.music:
                self._start(at, 'music_interval')
        if name == 'Status':
            flags = data.get('flags', {})
            flags = flags if isinstance(flags,dict) else {}
            self.status_at = at
            self.danger = flags.get('InDanger') is True
            self.vehicle = 'fighter' if flags.get('InFighter') else 'mothership' if flags.get('InMainShip') else 'other'
            if self.danger:
                self._start(at, 'danger')
            if self.vehicle == 'mothership':
                self.mothership.update(shields_up=flags.get('ShieldsUp'), at=at,
                                       overheating=flags.get('OverHeating') is True)
                if self.danger and flags.get('OverHeating') and self.mothership.get('hull', 1) <= .5:
                    self._alert('heat_danger', 'Critical hull and overheating. Check heat management.', at)
        if name == 'VehicleSwitch':
            self.vehicle = {'Fighter': 'fighter', 'Mothership': 'mothership'}.get(data.get('To'), 'unknown')
            for fighter in self.fighters.values():
                if fighter.get('status') == 'launched':
                    fighter['pilot'] = 'commander' if self.vehicle == 'fighter' else 'npc'
        if name in ('InDanger','OutofDanger'):
            self.danger = name == 'InDanger'
            self.status_at = at
            if self.danger:
                self._start(at, 'danger_transition')
        if name == 'UnderAttack':
            self.threat_at = at
            self._start(at, 'under_attack')
        if name == 'ShipTargeted':
            if data.get('TargetLocked') is not True:
                self.target = None
            else:
                # Never carry fields across partial scans or target switches.
                fields = ('Ship', 'Ship_Localised', 'ScanStage', 'PilotName', 'PilotName_Localised',
                          'PilotRank', 'Faction', 'LegalStatus', 'Bounty', 'HullHealth',
                          'ShieldHealth', 'Subsystem', 'Subsystem_Localised', 'SubsystemHealth')
                self.target = {k: data[k] for k in fields if k in data}
                self.target['at'] = at
                identity = (data.get('Ship'), data.get('PilotName'))
                if self.encounter is not None and all(identity):
                    key = json.dumps(identity)
                    previous = self.encounter['targets'].get(key, {'first_seen': at})
                    self.encounter['targets'][key] = dict(previous, last_seen=at, ship=identity[0], pilot=identity[1])
                    if len(self.encounter['targets']) > 100:
                        self.encounter['targets'].pop(next(iter(self.encounter['targets'])))
        if name == 'ShieldState' and self.vehicle == 'mothership':
            previous = self.shield_journal
            up = data.get('ShieldsUp')
            if isinstance(up, bool):
                self.shield_journal = up
                self.mothership.update(shields_up=up, at=at)
                if up is False and previous is not False and self.phase == 'active':
                    self._count('shield_losses')
                    self._record('mothership_shield_loss', at)
                    if self.danger and now-self.status_at <= 15 and self.mothership.get('hull', 1) <= .75 and now-self.mothership.get('hull_at',float('-inf')) <= 30:
                        self._alert('shield_loss', 'Shields down with recorded hull damage. Disengage if needed.', at)
        if name == 'HullDamage' and number(data.get('Health'), 0, 1):
            value = data['Health']
            if data.get('Fighter') is True:
                # Journal HullDamage has no fighter ID. Assign only when unique.
                candidates = [f for f in self.fighters.values() if f.get('status') == 'launched']
                if len(candidates) == 1:
                    candidates[0].update(hull=value, hull_at=at)
            elif data.get('Fighter') is False or ('Fighter' not in data and data.get('PlayerPilot') is True and self.vehicle == 'mothership'):
                previous = self.mothership.get('hull', 1)
                self.mothership.update(hull=value, hull_at=at)
                if value < previous:
                    self.threat_at = at
                    self._start(at, 'mothership_damage')
                    if int(value*4) < int(previous*4):
                        self._count('hull_milestones')
                        self._record('mothership_hull', at, health=value)
                    if value <= .5 and previous > .5:
                        self._alert('hull_critical', 'Mothership hull critical. Consider disengaging.', at)
        if name == 'RepairAll':
            self.mothership.update(hull=1.0,hull_at=at)
        if name == 'Loadout' and self.vehicle != 'fighter':
            identity = data.get('ShipID')
            ship = data.get('Ship')
            key = ('id',identity) if identity is not None else ('ship',ship,data.get('ShipIdent')) if ship else None
            if key is not None and self.own_ship_key is not None and key != self.own_ship_key:
                if self.phase == 'active':
                    self._end(at, 'ship_changed')
                self.mothership.clear()
                self.fighters.clear()
                self.target = None
                self.shield_journal = None
                self.alerts.clear()
                self.scope_since = at
                self.music = self.danger = False
                self.threat_at = float('-inf')
            if key is not None:
                self.own_ship_key = key
            if identity is not None:
                self.ship_id = identity
            if self.vehicle == 'unknown' and isinstance(ship,str) and 'fighter' not in ship.casefold():
                self.vehicle = 'mothership'
            if number(data.get('HullHealth'), 0, 1):
                self.mothership.update(hull=data['HullHealth'], hull_at=at)
        if name in ('LaunchFighter', 'FighterDestroyed', 'FighterRebuilt', 'DockFighter'):
            identity = data.get('ID')
            # Rebuilt can use Loadout rather than ID; never guess between bays.
            if identity is not None:
                fighter = self.fighters.setdefault(identity, {})
                while len(self.fighters)>100:
                    self.fighters.pop(next(iter(self.fighters)))
                previous = fighter.get('status')
                if name == 'DockFighter' and fighter.get('pilot') == 'commander':
                    self.vehicle = 'mothership'
                state = {'LaunchFighter':'launched', 'DockFighter':'docked',
                         'FighterDestroyed':'destroyed', 'FighterRebuilt':'ready'}[name]
                fighter.update(status=state, at=at)
                if name == 'LaunchFighter':
                    if data.get('PlayerControlled') is True:
                        self.vehicle = 'fighter'
                    fighter.update(pilot='commander' if data.get('PlayerControlled') is True else 'npc',
                                   loadout=data.get('Loadout'))
                    fighter.pop('hull', None)
                if previous != state:
                    counter = {'LaunchFighter':'fighter_launches', 'FighterDestroyed':'fighter_losses',
                               'FighterRebuilt':'fighter_rebuilds'}.get(name)
                    if counter:
                        self._count(counter)
                    self._record(name, at, fighter_id=identity)
                    if self.phase == 'active' and name == 'FighterDestroyed':
                        self._alert('fighter_destroyed', 'Fighter destroyed.', at, fighter_id=identity)
                    if self.phase == 'active' and name == 'FighterRebuilt' and previous == 'destroyed':
                        self._alert('fighter_rebuilt', 'Replacement fighter ready.', at, fighter_id=identity)
        if name == 'Bounty':
            self.threat_at = at
            self._start(at, 'bounty_award')
            reward = data.get('TotalReward')
            if not number(reward):
                rewards = data.get('Rewards', [])
                rewards = rewards if isinstance(rewards,list) else []
                values = [r['Reward'] for r in rewards if isinstance(r,dict) and number(r.get('Reward'))]
                reward = sum(values) if values else None
            self._count('bounty_awards')
            if reward is None:
                self._count('unknown_bounty_awards')
            else:
                self._count('bounty_credits',reward)
            self._record('bounty_award', at, credits=reward, target_ship=data.get('Target'))
            # Bounty.Target is a ship class, not proof the current target died.
        self.tick(now)
        return True

    def snapshot(self, now):
        self.tick(now)
        target = deepcopy(self.target)
        if target:
            target['age_seconds'] = max(0, now-target['at'])
            target['stale'] = now-target['at'] > self.TARGET_TTL
            stage = target.get('ScanStage')
            target['scan_complete'] = isinstance(stage,int) and not isinstance(stage,bool) and stage >= 3
        ship = deepcopy(self.mothership)
        for field in ('at','hull_at'):
            if field in ship:
                ship[field+'_age_seconds'] = max(0,now-ship[field])
                ship[field+'_stale'] = now-ship[field]>15
        fighters = deepcopy(self.fighters)
        for fighter in fighters.values():
            fighter['status_age_seconds'] = max(0,now-fighter['at'])
            if 'hull_at' in fighter:
                fighter['hull_age_seconds'] = max(0,now-fighter['hull_at'])
                fighter['hull_stale'] = now-fighter['hull_at']>15
        return dict(phase=self.phase, vehicle=self.vehicle,
                    status_age_seconds=max(0,now-self.status_at) if math.isfinite(self.status_at) else None,
                    evidence_stale=now-self.last_live_at>45,
                    focus_rule='Music is a last-known state until an explicit transition/boundary; stale focus is conservative, not proof of a current fight.',
                    mothership=ship, fighters=fighters, target=target, session=deepcopy(self.totals),
                    encounter=deepcopy(self.encounter), recent_encounters=deepcopy(list(self.records)),
                    limitations=['No own shield percentage, positions, velocities, DPS, accuracy or capacitor telemetry.',
                                 'Focus intervals are not individual kills; bounty awards may include shared credit.',
                                 'Unidentified targets and fighter damage without a unique fighter remain unknown.'])

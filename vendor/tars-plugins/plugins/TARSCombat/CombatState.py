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

    def __init__(self, observer=None):
        self.observer = observer
        self._heat_diagnostic_reason = None
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

    def _diagnose(self, stage, **fields):
        try:
            if self.observer is not None:
                self.observer(stage, **fields)
        except Exception:
            pass  # Diagnostics cannot participate in tracker decisions.

    def _rejected(self, data, reason, at=None, now=None):
        name = data.get('event') if isinstance(data, dict) else None
        if (name in ('FighterDestroyed','FighterRebuilt','ShieldState','HullDamage') or
            name=='Status' and isinstance(data.get('flags'),dict) and data['flags'].get('OverHeating')):
            fields = dict(event_type=name, reason=reason, outcome='rejected')
            if at is not None:
                fields.update(source_time=at, source_age_ms=(now-at)*1000)
            self._diagnose('combat_telemetry_rejected', **fields)

    def _removed(self, alert, reason):
        self._diagnose('combat_alert_removed', code=alert['code'], created=alert['created'], reason=reason)

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
        retained = []
        for alert in self.alerts:
            if alert['expires'] > now and self.alert_valid(alert, now):
                retained.append(alert)
            else:
                self._removed(alert, 'expired' if alert['expires'] <= now else
                              'combat_context_lost' if self.phase != 'active' else 'condition_changed')
        self.alerts = retained

    def _alert(self, code, text, at, **context):
        if at - self.last_alert.get(code, float('-inf')) < 30:
            self._diagnose('combat_alert_not_created', code=code, source_time=at, reason='cooldown')
            return
        self.last_alert[code] = at
        self.alerts.append(dict(code=code, text=text, created=at, expires=at+5, **context))
        self._diagnose('combat_alert_created', code=code, created=at, source_time=at)

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
            self._rejected(data, 'historic' if historic else 'invalid_telemetry')
            return False
        at = stamp(data.get('timestamp'))
        # Missing/future/stale events cannot enter live combat or create alerts.
        if at is None or not -2 <= now - at <= 30:
            self._rejected(data, 'invalid_timestamp' if at is None else
                           'future_telemetry' if now-at < -2 else 'stale_telemetry', at, now)
            return False
        if at < self.scope_since:
            self._rejected(data, 'before_scope', at, now)
            return False
        name = data.get('event')
        channel = ('target' if name == 'ShipTargeted' else 'fighter:' + str(data.get('ID'))
                   if name in ('LaunchFighter', 'DockFighter', 'FighterDestroyed', 'FighterRebuilt') else
                   'hull:' + str(data.get('Fighter')) if name == 'HullDamage' else str(name))
        if at < self.watermarks.get(channel, float('-inf')):
            self._rejected(data, 'out_of_order', at, now)
            return False
        signature = hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
        if signature in self.seen:
            self._rejected(data, 'duplicate_telemetry', at, now)
            return False
        self.seen[signature] = True
        while len(self.seen) > 2048:
            self.seen.pop(next(iter(self.seen)))
        self.watermarks[channel] = at
        self.last_live_at = max(self.last_live_at, at)
        if name in ('FighterDestroyed','FighterRebuilt','ShieldState','HullDamage'):
            self._diagnose('combat_telemetry_accepted', event_type=name, source_time=at,
                           source_age_ms=(now-at)*1000, fighter_identity_known=data.get('ID') is not None)
        self.tick(now)
        if name in ('LoadGame', 'Shutdown', 'Died', 'FSDJump', 'SupercruiseEntry', 'Docked'):
            self.scope_since = at
            if self.phase == 'active':
                self._end(at, name)
            self.music = self.danger = False
            self.threat_at = float('-inf')
            self.target = None
            for alert in self.alerts: self._removed(alert, 'scope_reset')
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
            if flags.get('OverHeating') and not (self.vehicle=='mothership' and self.danger and self.mothership.get('hull',1)<=.5):
                reason = ('mothership_context_unconfirmed' if self.vehicle!='mothership' else
                          'missing_combat_context' if not self.danger else 'critical_hull_unconfirmed')
                if reason != self._heat_diagnostic_reason:
                    self._diagnose('combat_alert_not_created',code='heat_danger',reason=reason)
                self._heat_diagnostic_reason=reason
            else:
                self._heat_diagnostic_reason=None
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
                    else:
                        self._diagnose('combat_alert_not_created',code='shield_loss',reason='danger_or_damage_unconfirmed')
                elif up is False:
                    self._diagnose('combat_alert_not_created',code='shield_loss',reason='unchanged_shield_state' if previous is False else 'missing_combat_context')
        elif name == 'ShieldState' and data.get('ShieldsUp') is False:
            self._diagnose('combat_alert_not_created',code='shield_loss',reason='mothership_context_unconfirmed')
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
                    elif value <= .5:
                        self._diagnose('combat_alert_not_created',code='hull_critical',reason='threshold_already_crossed')
                elif value <= .5:
                    self._diagnose('combat_alert_not_created',code='hull_critical',reason='hull_not_decreasing')
            elif value <= .5:
                self._diagnose('combat_alert_not_created',code='hull_critical',reason='mothership_context_unconfirmed')
        elif name == 'HullDamage':
            self._diagnose('combat_alert_not_created',code='hull_critical',reason='invalid_hull_telemetry')
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
                for alert in self.alerts: self._removed(alert, 'scope_reset')
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
            if name in ('FighterDestroyed','FighterRebuilt') and identity is None:
                self._diagnose('combat_alert_not_created', event_type=name,
                               reason='missing_fighter_identity', fighter_identity_known=False)
            if identity is not None:
                try:
                    hash(identity)
                except TypeError:
                    self._diagnose('combat_alert_not_created', event_type=name,
                                   reason='invalid_fighter_identity', fighter_identity_known=True)
                    # Preserve the original dictionary-key failure below.
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
                    if name in ('FighterDestroyed','FighterRebuilt') and self.phase != 'active':
                        self._diagnose('combat_alert_not_created', event_type=name, reason='missing_combat_context')
                    elif name == 'FighterRebuilt' and previous != 'destroyed':
                        self._diagnose('combat_alert_not_created', event_type=name, reason='prior_loss_unconfirmed')
                elif name in ('FighterDestroyed','FighterRebuilt'):
                    self._diagnose('combat_alert_not_created', event_type=name, reason='unchanged_fighter_state')
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

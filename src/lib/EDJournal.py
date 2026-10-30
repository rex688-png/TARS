import io
import json
from os import listdir
import os
from os.path import join, isfile, getmtime
from queue import Queue
import threading
from time import sleep
import traceback
from typing import TypedDict

from .Logger import log

class JournalEntry(TypedDict):
    id: str
    timestamp: str
    event: str

class EDJournal:
    def __init__(self, logs_path: str):
        self.events: Queue[JournalEntry] = Queue()
        self.logs_path: str = logs_path
        
        self.historic_events: list[JournalEntry] = []
        self._stop_event = threading.Event()
        self._line_checkpoints: dict[str, int] = {}
        self.load_history()
        
        thread = threading.Thread(target=self._reading_thread)
        thread.daemon = True
        self._reader_thread = thread
        thread.start()
    
    def get_event_id(self, log: str, file_index: int) -> str:
        return log.replace('\\', '/').split('/')[-1] + '.' + str(file_index).zfill(6)
        
    def augment_event(self, entry: JournalEntry) -> JournalEntry:
        if entry.get('event') == "NavRoute":
            entry = self.augment_event_from_file(entry, "NavRoute.json")
        if entry.get('event') == "Market":
            entry = self.augment_event_from_file(entry, "Market.json")
        if entry.get('event') == "Outfitting":
            entry = self.augment_event_from_file(entry, "Outfitting.json")
        if entry.get('event') == "Shipyard":
            entry = self.augment_event_from_file(entry, "Shipyard.json")
        if entry.get('event') == "Cargo":
            entry = self.augment_event_from_file(entry, "Cargo.json")
        if entry.get('event') == "ModuleInfo":
            entry = self.augment_event_from_file(entry, "ModulesInfo.json")
        if entry.get('event') == "ShipLocker":
            entry = self.augment_event_from_file(entry, "ShipLocker.json")
        if entry.get('event') == "Backpack":
            entry = self.augment_event_from_file(entry, "Backpack.json")
        return entry

    def augment_event_from_file(self, entry: JournalEntry, filename: str) -> JournalEntry:
        file_path = join(self.logs_path, filename)

        try:
            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    data = json.load(file)
            except json.JSONDecodeError:
                sleep(0.1)
                with open(file_path, 'r', encoding='utf-8') as file:
                    data = json.load(file)

            if data.get("timestamp") == entry.get("timestamp"):
                return {**entry, **data}
        except Exception as e:
            log('error', f"Failed to augment event {entry.get('event')} with data from {filename}", e, traceback.format_exc())
        return entry
        
    def load_history(self):
        latest_log = self.get_latest_log()
        if latest_log is None:
            return

        with open(latest_log, 'r', encoding='utf-8') as f:
            file_index = 0
            # read the file from start to finish, line by line
            for line in f:
                if not line.endswith("\n"):
                    break  # The writer may still be appending this record.
                #log("debug", f"Loading history from {latest_log} at line {file_index}")
                file_index += 1
                try:
                    entry: JournalEntry = json.loads(line)
                    if not isinstance(entry, dict):
                        raise ValueError('Journal record is not an object')
                    entry['id'] = self.get_event_id(latest_log, file_index)
                    entry = self.augment_event(entry)

                    self.historic_events.append(entry)
                except ValueError:
                    continue
            self._line_checkpoints[latest_log] = file_index
            log("debug", f"Loaded {len(self.historic_events)} historicevents from {latest_log}")
                
    def stop(self):
        """Stop polling without waiting for the next retry delay."""
        self._stop_event.set()
        if threading.current_thread() is not self._reader_thread:
            self._reader_thread.join(timeout=2)

    def _reading_thread(self):
        while not self._stop_event.is_set():
            try:
                self._reading_loop()
            except Exception:
                # Do not log journal records or paths with commander information.
                log('error', 'Journal reader failed; retrying from last consumed line')
                if self._stop_event.wait(1):
                    break

    def _reading_loop(self):
        while not self._stop_event.is_set():
            latest_log = self.get_latest_log()
            if latest_log is None:
                self._stop_event.wait(1)
                continue
            with open(latest_log, 'r', encoding='utf-8') as f:
                file_index = 0
                while not self._stop_event.is_set():
                    position = f.tell()
                    line = f.readline()
                    if not line or not line.endswith('\n'):
                        # readline at EOF is nonblocking. Keep an incomplete record
                        # at its original offset until the writer finishes it.
                        f.seek(position)
                        if latest_log != self.get_latest_log():
                            break
                        self._stop_event.wait(0.01)
                        continue
                    file_index += 1
                    if file_index <= self._line_checkpoints.get(latest_log, 0):
                        continue
                    try:
                        entry: JournalEntry = json.loads(line)
                        if not isinstance(entry, dict):
                            raise ValueError('Journal record is not an object')
                        entry['id'] = self.get_event_id(latest_log, file_index)
                        entry = self.augment_event(entry)
                    except (json.JSONDecodeError, ValueError):
                        # A complete malformed record must not block later records.
                        self._line_checkpoints[latest_log] = file_index
                        continue
                    self.events.put(entry)
                    self._line_checkpoints[latest_log] = file_index
                    # Keep reconnect cursors bounded across long sessions/rotations.
                    if len(self._line_checkpoints) > 32:
                        del self._line_checkpoints[next(iter(self._line_checkpoints))]
            self._stop_event.wait(0.01)

    def get_latest_log(self):
        try:
            list_of_logs = [join(self.logs_path, f) for f in listdir(self.logs_path) if
                            isfile(join(self.logs_path, f)) and f.startswith('Journal.')]
        except:
            return None
        if not list_of_logs:
            return None
        latest_log = max(list_of_logs, key=getmtime)
        return latest_log



def main():
    jn = EDJournal({})
    while True:
        sleep(0.1)
        while not jn.events.empty():
            print(jn.events.get())


if __name__ == "__main__":
    main()

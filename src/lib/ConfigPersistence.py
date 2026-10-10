"""Small atomic JSON store for the existing TARS profile and previous-good backup."""
import json
import os
from pathlib import Path
import tempfile

def valid_profile(data):
    return (isinstance(data,dict) and type(data.get('config_version')) is int
            and isinstance(data.get('characters'),list) and isinstance(data.get('plugin_settings'),dict))

def valid_restore_profile(data):
    # Keep normal save/legacy recovery permissive; reject unsafe manual imports.
    return (valid_profile(data) and data['config_version'] >= 0 and bool(data['characters'])
            and all(isinstance(character,dict) and isinstance(character.get('name'),str)
                    and bool(character['name'].strip()) for character in data['characters'])
            and type(data.get('active_character_index',0)) is int
            and -1 <= data.get('active_character_index',0) < len(data['characters'])
            and all(isinstance(key,str) and isinstance(value,dict)
                    for key,value in data['plugin_settings'].items())
            and isinstance(data.get('action_permissions',{}),dict)
            and all(isinstance(key,str) and value in ('allow','ask','block')
                    for key,value in data.get('action_permissions',{}).items()))

def read_valid(path):
    data=json.loads(Path(path).read_text(encoding='utf-8'))
    if not valid_profile(data):
        raise ValueError('Invalid TARS profile structure')
    return data

def atomic_bytes(path,content):
    path=Path(path)
    fd,temp=tempfile.mkstemp(prefix='.config-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(content);stream.flush();os.fsync(stream.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def save_profile(config,path='config.json'):
    if not valid_profile(config):
        raise ValueError('Invalid TARS profile; working config retained')
    main=Path(path); backup=main.with_name('config.backup.json')
    payload=(json.dumps(config,indent=4,ensure_ascii=False)+'\n').encode('utf-8')
    if main.exists():
        try:
            existing=main.read_bytes()
            if valid_profile(json.loads(existing)):
                atomic_bytes(backup,existing)
        except (ValueError,UnicodeError):
            pass  # Preserve the previous known-good backup when main is corrupt.
    atomic_bytes(main,payload)

def recover_profile(path='config.json'):
    main=Path(path); backup=main.with_name('config.backup.json')
    previous=read_valid(backup)
    # Keep the broken file for local investigation; never export it in diagnostics.
    if main.exists():
        damaged=main.with_name('config.corrupt.json')
        os.replace(main,damaged)
    atomic_bytes(main,backup.read_bytes())
    return previous

def create_manual_backup(path='config.json'):
    main=Path(path); payload=main.read_bytes()
    if not valid_restore_profile(json.loads(payload)):
        raise ValueError('Current profile invalid')
    atomic_bytes(main.with_name('config.manual-backup.json'),payload)

def restore_manual_backup(path='config.json'):
    main=Path(path); candidate=read_valid(main.with_name('config.manual-backup.json'))
    if not valid_restore_profile(candidate):
        raise ValueError('Manual backup has invalid TARS profile structure')
    save_profile(candidate,main)
    return candidate

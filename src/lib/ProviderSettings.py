"""Provider schema initialization preserves explicit saved tuning."""
from copy import deepcopy


def migrate_provider_settings(plugin) -> bool:
    before = deepcopy(plugin.settings)
    try:
        version = max(0, int(before.get('settings_version', 0)))
    except (TypeError, ValueError):
        version = 0
    target = max(0, int(plugin.settings_schema_version))
    while version < target:
        plugin.migrate_settings(plugin.settings, version)
        version += 1
        plugin.settings['settings_version'] = version
    if plugin.model_providers:
        # Packages initialize absent fields. Saved user values win, even when
        # they equal a previous default. Schema metadata remains upgradeable.
        plugin.settings.update({key: value for key, value in before.items()
                                if key != 'settings_version'})
    return plugin.settings != before

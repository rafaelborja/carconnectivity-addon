
- **Volkswagen NA**: new `myVW region` option (`auto`/`us`/`ca`). `auto` keeps the previous behaviour (region taken from the Home Assistant country), `us`/`ca` force the backend region without expert mode.
- **Volkswagen NA**: new `Register the PIN code` option, off by default. Enable it when the myVW S-PIN service answers `403`/`404` on the SPIN challenge so the connector registers the configured PIN on the account before retrying.

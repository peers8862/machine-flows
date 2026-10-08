# service-settings/ (example layout)

Shared settings, one folder per service, synced between machines. It stays local because real settings name accounts and projects.

```
service-settings/
  mach/
    config.toml              # shared mach config; start from mach/config/config.example.toml
    hosts/<host>.toml        # per-machine overrides
    docs-history.local.py    # personal, machine-specific; gitignored (*.local.*)
```

Rules:

- No secrets. Settings reference credentials by environment-variable name or helper script path only. Secrets that `mach` needs live in unsynced `~/.config/mach/secrets.toml` (see `examples/secrets.toml.example`).
- Precedence in mach: command-line flags, environment, `~/.config/mach/local.toml`, `hosts/<host>.toml`, `config.toml`, built-in defaults.
- mach works with no config file at all.

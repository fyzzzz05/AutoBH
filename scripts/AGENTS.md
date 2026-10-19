# macOS local installation artifacts

User feedback (2026-10-19, supersedes the earlier single-backup policy): do not retain any old AutoBH App bundles or compressed rollback packages after successful installation. During the install transaction only, keep a temporary previous bundle so a failed replacement can be undone; remove it on success. Never create dated `.app` backups or `previous.zip`. Source rollback should use verified Git history; never assume history exists without checking it.

For local updates, prepare signed release assets first, quit only the GUI, and use `scripts/install_macos.py`; reopen the installed App and verify originally running workers recover. After verification, run `scripts/cleanup_macos.py --apply` to trash inactive generated app/test copies, legacy rollback archives and old release packages. Never empty Trash, touch real account/cache directories, or move a running app/engine. Keep only the installed current App and current distribution assets.

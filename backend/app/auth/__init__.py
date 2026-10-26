"""Sign-in, roles and the audit log.

Users, sessions and audit entries live in a small SQLite file (config.AUTH_DB_PATH),
separate from the analysis outputs, so re-running the pipeline never touches them.
"""

# Managed local object store

OiiOii retains final compressed films in a private SHA-256 content-addressed object
store. The database remains the authority for the artifact catalog, quota, owner,
hash, compression profile, access control, and audit history; it does not retain a
second full MP4 BLOB for new work.

On Windows the default production object root is
`D:\oioi-data\object-store\oioi-films`. Override it with
`FILM_PIPELINE_OBJECT_STORE_PATH`. Existing BLOB artifacts are migrated safely at
store startup: the object is atomically written and fsynced before its legacy BLOB
is cleared; the one-time SQLite `VACUUM` then releases old BLOB pages back to the
disk. Set `FILM_PIPELINE_MIGRATE_LEGACY_ARTIFACTS=false` to postpone that copy
operation, or `FILM_PIPELINE_VACUUM_AFTER_MIGRATION=false` to defer compaction.

The owner-authorized artifact endpoint reads the managed file through `FileResponse`,
preserving HTTP Range handling for MP4 playback. Objects are never statically mounted
or publicly enumerable. EmergentSH uses the parallel root
`D:\oioi-data\object-store\emergentsh-apps` for compressed generated-app ZIPs.

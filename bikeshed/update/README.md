Adding New Update Folders/Files
===============================

When adding new folders, files, or types of updateable data entirely,
make sure to update `manifest.py`'s
`knownFiles` (for top-level files)
and `knownFolders` (for top-level folders),
so it knows where to look when generating manifests.

Also update `main.py`'s `cleanupFiles()`,
so it knows where it can *delete* files,
otherwise phantom paths will stick around over time.
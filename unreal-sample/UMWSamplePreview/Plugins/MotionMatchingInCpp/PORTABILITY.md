# MotionMatchingInCpp migration notes

This plugin intentionally does not set a host project's default map, input
settings, project identifier, asset-manager scan roots, or editor preferences.
Those settings belong to the project that installs the plugin.

Before enabling the plugin in a new project, make sure the project enables the
engine plugins listed in `MotionMatchingInCpp.uplugin`. Configure the project's
own GameMode, Pawn, PlayerController, Enhanced Input assets, maps, and optional
touch interface.

The plugin content currently contains five packages with legacy `ZeroG` asset
references: `DefaultLevel.umap` and four `CHT_PoseSearchDatabases` packages.
Open these packages in Unreal Editor after migration, replace the affected
ZeroG classes or assets with equivalents from the destination project, then
save the packages. Do not attempt to edit `.uasset` or `.umap` binaries
directly.

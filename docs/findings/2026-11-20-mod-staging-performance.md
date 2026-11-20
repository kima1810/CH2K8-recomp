# Mod staging performance and progress

The implemented staging path is `New-ChmodCache` in `tools/chmod.ps1`.
`Get-ChmodCacheKey` identifies reusable prepared output. A matching prepared cache
is returned before bank staging and native preparation. This avoids repeating
unchanged reconstruction on warm launches; it does not bypass package validation.

The staging path supports sparse cache initialization through the native tools,
then stages affected banks and applies declared files. It prepares the runtime
asset map after replacement. A cache lock prevents concurrent launchers from
publishing competing preparations. The key is checked again before publication
so changed inputs reject the result. Cleanup only targets recognized published
cache receipts, preserving unrelated folders.

`Write-ChmodProgress` publishes checking/reuse, bank staging, file application
and native asset-map preparation phases. Counted work reports done/total, and the
progress file is passed to native preparation. This supplies the launcher's
staging progress display without doing filesystem polling in gameplay draw hooks.

Full package integrity checks and update downloads remain synchronous in the Mods
view, as recorded in the [loader audit](2026-11-12-modloader-audit.md). Cold staging
still costs I/O and native conversion work. A recursive collection removes a
single aggregate package-size constraint; it does not guarantee constant-time
preparation or remove each child's validation limits.

This record is based on source inspection. No new cold/warm launch timing,
frame-time benchmark or full-overhaul scale test was performed for this PR.
Existing performance evidence is indexed in
[the research record](../research/zmo-beta-research.md).

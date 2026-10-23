$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$planPath = Join-Path $PSScriptRoot 'out/step17/cache_prune_dry_run.json'
$auditPath = Join-Path $PSScriptRoot 'out/step17/cache_prune_audit.json'
$expectedHash = 'f7956e2fead2ff25601019908304b3d6de0ecf29811e358bc05870c15d21d793'
if ((Get-FileHash -LiteralPath $planPath -Algorithm SHA256).Hash.ToLowerInvariant() -ne $expectedHash) {
    throw 'STOP: approved dry-run file changed'
}
$plan = Get-Content -LiteralPath $planPath -Raw -Encoding UTF8 | ConvertFrom-Json
$audit = Get-Content -LiteralPath $auditPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($audit.plan_sha256 -ne $expectedHash) { throw 'Audit does not match approved plan' }
$byPath = @{}
foreach ($entry in $plan.candidates) { $byPath[$entry.path] = $entry }
$files = @()
$folders = @{}
foreach ($entry in $audit.approved) {
    $original = $byPath[$entry.path]
    if (!$original -or $entry.exclusion_reasons.Count -or $original.files.Count -ne $entry.files.Count) {
        throw "Audit is not a subset of the approved list: $($entry.path)"
    }
    $folder = [IO.Path]::GetFullPath((Join-Path $workspace $entry.path))
    $cachePrefix = (Join-Path $workspace '.cache') + [IO.Path]::DirectorySeparatorChar
    if (!$folder.StartsWith($cachePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Folder outside project cache: $folder"
    }
    $folders[$folder] = $true
    for ($i = 0; $i -lt $entry.files.Count; $i++) {
        $item = $entry.files[$i]
        $saved = $original.files[$i]
        if ($item.path -ne $saved.path -or $item.bytes -ne $saved.bytes -or $item.mtime_ns -ne $saved.mtime_ns) {
            throw 'Audit file differs from original approved list'
        }
        $absolute = [IO.Path]::GetFullPath((Join-Path $workspace $item.path))
        if (!$absolute.StartsWith($folder + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) {
            throw "File outside approved folder: $absolute"
        }
        $actual = Get-Item -LiteralPath $absolute -Force
        # Python's Windows st_mtime_ns is FILETIME ticks since the Unix epoch, times 100.
        $mtime = ($actual.LastWriteTimeUtc.ToFileTimeUtc() - 116444736000000000L) * 100L
        if (($actual.Attributes -band [IO.FileAttributes]::ReparsePoint) -or $actual.Length -ne $item.bytes -or $mtime -ne $item.mtime_ns) {
            throw "STOP: approved file changed since dry run: $absolute"
        }
        $files += [PSCustomObject]@{ Path = $absolute; Bytes = $item.bytes }
        $parent = [IO.Path]::GetDirectoryName($absolute)
        while ($parent -ne $folder) {
            $folders[$parent] = $true
            $parent = [IO.Path]::GetDirectoryName($parent)
        }
    }
}
# All listed paths/stats were checked before the first deletion. Never discover extra
# candidates or recursively remove a directory; unlisted files therefore remain intact.
$started = [DateTimeOffset]::UtcNow
$deletedFiles = 0
$deletedFolders = 0
$deletedBytes = 0L
$failure = $null
try {
    foreach ($item in $files) {
        Remove-Item -LiteralPath $item.Path -Force
        $deletedFiles++
        $deletedBytes += $item.Bytes
    }
    foreach ($folder in ($folders.Keys | Sort-Object Length -Descending)) {
        [IO.Directory]::Delete($folder, $false)
        $deletedFolders++
    }
} catch {
    $failure = $_.Exception.Message
    throw
} finally {
    $ended = [DateTimeOffset]::UtcNow
    $drive = [IO.DriveInfo]::new([IO.Path]::GetPathRoot($workspace))
    $record = [ordered]@{
        plan_sha256 = $expectedHash
        original_folders = $plan.candidates.Count
        excluded_folders = $audit.excluded.Count
        selected_folders = $audit.approved.Count
        deleted_files = $deletedFiles
        deleted_directories_including_image_subfolders = $deletedFolders
        deleted_bytes = $deletedBytes
        started_utc = $started.ToString('o')
        finished_utc = $ended.ToString('o')
        elapsed_seconds = ($ended - $started).TotalSeconds
        free_bytes_after = $drive.AvailableFreeSpace
        error = $failure
    }
    $record | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'out/step17/cache_deletion_record.json') -Encoding UTF8
    $record | ConvertTo-Json -Depth 5
}

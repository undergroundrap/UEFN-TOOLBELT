[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("prepare", "restore", "status")]
    [string]$Action,

    [string]$Project = "",

    [string]$ProjectsRoot = (Join-Path ([Environment]::GetFolderPath("MyDocuments")) "Fortnite Projects"),

    [string]$StashRoot = (Join-Path $env:LOCALAPPDATA "UEFN-Toolbelt\SessionPythonStash")
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Get-FullPath([string]$Path) {
    return [IO.Path]::GetFullPath($Path)
}

function Test-ChildPath([string]$Parent, [string]$Child) {
    $parentFull = Get-FullPath $Parent
    $childFull = Get-FullPath $Child
    return $childFull.StartsWith(
        $parentFull.TrimEnd('\') + '\',
        [StringComparison]::OrdinalIgnoreCase
    )
}

function Get-UefnProjects([string]$Root) {
    if (-not (Test-Path -LiteralPath $Root -PathType Container)) {
        throw "Fortnite Projects folder not found: $Root"
    }

    return @(
        Get-ChildItem -LiteralPath $Root -Directory -Force |
            Where-Object {
                @(Get-ChildItem -LiteralPath $_.FullName -File -Filter '*.uefnproject' -Force).Count -gt 0
            } |
            Sort-Object Name
    )
}

function Resolve-ProjectPath([string]$Root, [string]$Requested) {
    $rootFull = Get-FullPath $Root
    if ($Requested) {
        $candidate = if (Test-Path -LiteralPath $Requested -PathType Container) {
            Get-FullPath $Requested
        } else {
            Get-FullPath (Join-Path $rootFull $Requested)
        }
        if (-not (Test-ChildPath $rootFull $candidate)) {
            throw "Project must be inside Fortnite Projects: $candidate"
        }
        if (-not (Test-Path -LiteralPath $candidate -PathType Container)) {
            throw "UEFN project not found: $candidate"
        }
        if (@(Get-ChildItem -LiteralPath $candidate -File -Filter '*.uefnproject' -Force).Count -eq 0) {
            throw "Folder has no .uefnproject file: $candidate"
        }
        return $candidate
    }

    $projects = @(Get-UefnProjects $rootFull)
    if ($projects.Count -eq 0) {
        throw "No UEFN projects found under: $rootFull"
    }
    if ($projects.Count -eq 1) {
        Write-Host "Only one UEFN project found - selecting $($projects[0].Name)."
        return $projects[0].FullName
    }

    Write-Host "UEFN projects:"
    for ($index = 0; $index -lt $projects.Count; $index++) {
        Write-Host ("  [{0}] {1}" -f ($index + 1), $projects[$index].Name)
    }
    $choice = Read-Host "Select a project"
    $number = 0
    if (-not [int]::TryParse($choice, [ref]$number) -or $number -lt 1 -or $number -gt $projects.Count) {
        throw "Invalid project selection: $choice"
    }
    return $projects[$number - 1].FullName
}

function Get-StashPath([string]$Base, [string]$ProjectPath) {
    $projectName = Split-Path -Leaf $ProjectPath
    return Get-FullPath (Join-Path (Get-FullPath $Base) $projectName)
}

function Get-PythonFiles([string]$Root) {
    return @(
        Get-ChildItem -LiteralPath $Root -Recurse -File -Filter '*.py' -Force -ErrorAction Stop
    )
}

function Write-StashManifest(
    [string]$ManifestPath,
    [string]$ProjectPath,
    [string[]]$RelativeFiles,
    [string]$State
) {
    $manifest = [ordered]@{
        schema_version = 2
        state = $State
        project_path = $ProjectPath
        prepared_at = (Get-Date).ToString('o')
        file_count = $RelativeFiles.Count
        relative_files = @($RelativeFiles)
    }
    $manifest | ConvertTo-Json -Depth 4 |
        Set-Content -LiteralPath $ManifestPath -Encoding UTF8
}

function Prepare-Project([string]$ProjectPath, [string]$StashPath) {
    if (Test-Path -LiteralPath $StashPath) {
        throw "An active Python stash already exists. Restore it first: $StashPath"
    }
    if (Test-ChildPath $ProjectPath $StashPath) {
        throw "The Python stash must be outside the UEFN project: $StashPath"
    }

    $pythonFiles = @(Get-PythonFiles $ProjectPath)
    if ($pythonFiles.Count -eq 0) {
        Write-Host "READY: no .py files exist inside $ProjectPath"
        return
    }

    foreach ($pythonFile in $pythonFiles) {
        if (-not (Test-ChildPath $ProjectPath $pythonFile.FullName)) {
            throw "Refusing Python file outside the selected project: $($pythonFile.FullName)"
        }
    }

    $relativeFiles = @(
        $pythonFiles | ForEach-Object {
            $_.FullName.Substring($ProjectPath.Length).TrimStart('\')
        }
    )
    $dataPath = Get-FullPath (Join-Path $StashPath 'files')
    $manifestPath = Join-Path $StashPath 'manifest.json'
    $moved = [System.Collections.Generic.List[object]]::new()
    try {
        New-Item -ItemType Directory -Path $dataPath -Force | Out-Null
        # Write recovery metadata before moving anything. If the process is
        # interrupted, restore can distinguish files already moved from files
        # that never left the project.
        Write-StashManifest $manifestPath $ProjectPath $relativeFiles 'preparing'

        foreach ($pythonFile in $pythonFiles) {
            $relativePath = $pythonFile.FullName.Substring($ProjectPath.Length).TrimStart('\')
            $destination = Get-FullPath (Join-Path $dataPath $relativePath)
            if (-not (Test-ChildPath $dataPath $destination)) {
                throw "Refusing destination outside the stash: $destination"
            }
            if (Test-Path -LiteralPath $destination) {
                throw "Stash collision: $destination"
            }
            New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
            Move-Item -LiteralPath $pythonFile.FullName -Destination $destination
            $moved.Add([pscustomobject]@{
                source = $pythonFile.FullName
                destination = $destination
                relative_path = $relativePath
            }) | Out-Null
        }

        $remaining = @(Get-PythonFiles $ProjectPath)
        if ($remaining.Count -ne 0) {
            throw "Prepare verification failed: $($remaining.Count) .py files remain in the project."
        }

        Write-StashManifest $manifestPath $ProjectPath $relativeFiles 'prepared'
    } catch {
        $prepareError = $_
        $movedItems = @($moved)
        [array]::Reverse($movedItems)
        foreach ($item in $movedItems) {
            if ((Test-Path -LiteralPath $item.destination -PathType Leaf) -and
                -not (Test-Path -LiteralPath $item.source)) {
                New-Item -ItemType Directory -Path (Split-Path -Parent $item.source) -Force |
                    Out-Null
                Move-Item -LiteralPath $item.destination -Destination $item.source -ErrorAction SilentlyContinue
            }
        }

        $rollbackIncomplete = @(
            $moved | Where-Object {
                (Test-Path -LiteralPath $_.destination -PathType Leaf) -or
                -not (Test-Path -LiteralPath $_.source -PathType Leaf)
            }
        )
        if ($rollbackIncomplete.Count -eq 0) {
            if (Test-Path -LiteralPath $StashPath -PathType Container) {
                Remove-Item -LiteralPath $StashPath -Recurse -Force
            }
            throw "Prepare failed and all moved files were rolled back: $($prepareError.Exception.Message)"
        }

        # The prewritten 'preparing' manifest remains usable by restore: files
        # already rolled back are skipped, while residual stashed files return.
        throw "Prepare failed and rollback is incomplete. Run restore_after_launch.bat before retrying. Original error: $($prepareError.Exception.Message)"
    }

    Write-Host "READY: moved $($moved.Count) Python files outside the UEFN project."
    Write-Host "Stash: $StashPath"
    Write-Host "Launch Session or Push Changes now. Run restore_after_launch.bat afterward."
}

function Restore-Project([string]$ProjectPath, [string]$StashPath) {
    $manifestPath = Join-Path $StashPath 'manifest.json'
    if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
        throw "No active Python stash manifest found: $manifestPath"
    }

    $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    $manifestProject = Get-FullPath ([string]$manifest.project_path)
    if ($manifestProject -ne (Get-FullPath $ProjectPath)) {
        throw "Stash belongs to '$manifestProject', not '$ProjectPath'."
    }

    $relativeFiles = @($manifest.relative_files)
    if ($relativeFiles.Count -ne [int]$manifest.file_count) {
        throw "Stash manifest count is inconsistent; refusing a partial restore."
    }

    $schemaVersion = if ($null -ne $manifest.PSObject.Properties['schema_version']) {
        [int]$manifest.schema_version
    } else {
        1
    }
    $state = if ($null -ne $manifest.PSObject.Properties['state']) {
        [string]$manifest.state
    } else {
        'prepared'
    }
    if ($state -notin @('preparing', 'prepared', 'restoring')) {
        throw "Unknown stash state '$state'; refusing restore."
    }
    $dataPath = if ($schemaVersion -ge 2) {
        Get-FullPath (Join-Path $StashPath 'files')
    } else {
        $StashPath
    }

    $restorePlan = @()
    foreach ($relativePath in $relativeFiles) {
        $source = Get-FullPath (Join-Path $dataPath ([string]$relativePath))
        $destination = Get-FullPath (Join-Path $ProjectPath ([string]$relativePath))
        if (-not (Test-ChildPath $dataPath $source)) {
            throw "Refusing source outside the stash: $source"
        }
        if (-not (Test-ChildPath $ProjectPath $destination)) {
            throw "Refusing destination outside the project: $destination"
        }
        $sourceExists = Test-Path -LiteralPath $source -PathType Leaf
        $destinationExists = Test-Path -LiteralPath $destination -PathType Leaf
        if ($sourceExists -and $destinationExists) {
            throw "Restore collision; project file already exists: $destination"
        }
        if ($sourceExists) {
            $restorePlan += [pscustomobject]@{ source = $source; destination = $destination }
        } elseif ($state -in @('preparing', 'restoring') -and $destinationExists) {
            continue
        } elseif ($destinationExists) {
            throw "Stashed file is missing: $source"
        } else {
            throw "Stashed file and project file are both missing: $relativePath"
        }
    }

    $restored = [System.Collections.Generic.List[object]]::new()
    try {
        if ($restorePlan.Count -gt 0 -and $state -ne 'restoring') {
            # Persist the resumable state before the first move. If PowerShell
            # or Windows stops mid-restore, the next run accepts both files
            # already back in the project and files still in the stash.
            if ($null -ne $manifest.PSObject.Properties['state']) {
                $manifest.state = 'restoring'
            } else {
                $manifest | Add-Member -NotePropertyName state -NotePropertyValue 'restoring'
            }
            $manifest | ConvertTo-Json -Depth 4 |
                Set-Content -LiteralPath $manifestPath -Encoding UTF8
            $state = 'restoring'
        }
        foreach ($item in $restorePlan) {
            New-Item -ItemType Directory -Path (Split-Path -Parent $item.destination) -Force |
                Out-Null
            Move-Item -LiteralPath $item.source -Destination $item.destination
            $restored.Add($item) | Out-Null
        }
    } catch {
        $restoredItems = @($restored)
        [array]::Reverse($restoredItems)
        foreach ($item in $restoredItems) {
            if ((Test-Path -LiteralPath $item.destination -PathType Leaf) -and
                -not (Test-Path -LiteralPath $item.source)) {
                New-Item -ItemType Directory -Path (Split-Path -Parent $item.source) -Force |
                    Out-Null
                Move-Item -LiteralPath $item.destination -Destination $item.source -ErrorAction SilentlyContinue
            }
        }
        throw
    }

    $unrestored = @(Get-PythonFiles $StashPath)
    if ($unrestored.Count -ne 0) {
        throw "Restore verification failed: $($unrestored.Count) Python files remain in the stash."
    }
    $missingRestored = @(
        $relativeFiles | Where-Object {
            -not (Test-Path -LiteralPath (Join-Path $ProjectPath ([string]$_)) -PathType Leaf)
        }
    )
    if ($missingRestored.Count -ne 0) {
        throw "Restore verification failed: $($missingRestored.Count) Python files are missing from the project."
    }
    $unexpectedFiles = @(
        Get-ChildItem -LiteralPath $StashPath -Recurse -File -Force -ErrorAction Stop |
            Where-Object { $_.FullName -ne $manifestPath }
    )
    if ($unexpectedFiles.Count -ne 0) {
        throw "Restore verification failed: unexpected files remain in the stash."
    }

    Remove-Item -LiteralPath $StashPath -Recurse -Force
    Write-Host "RESTORED: $($relativeFiles.Count) Python files are present in $ProjectPath"
}

$projectsRootFull = Get-FullPath $ProjectsRoot
$projectPath = Resolve-ProjectPath $projectsRootFull $Project
$stashPath = Get-StashPath $StashRoot $projectPath

switch ($Action) {
    'prepare' { Prepare-Project $projectPath $stashPath }
    'restore' { Restore-Project $projectPath $stashPath }
    'status' {
        $count = @(Get-PythonFiles $projectPath).Count
        Write-Host "Project Python files: $count"
        Write-Host "Active stash: $(Test-Path -LiteralPath $stashPath -PathType Container)"
        Write-Host "Stash path: $stashPath"
    }
}

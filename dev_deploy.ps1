# Dev Deploy Script - Deploy to local Kodi addon directory
# Usage: .\dev_deploy.ps1

# Fix encoding issue for UTF-8 (if file executed with proper encoding, but English is safer)
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

$SourceDir = $PSScriptRoot
$AppData = $env:APPDATA
$TargetDir = Join-Path $AppData "Kodi\addons\plugin.video.filteredmovies"

Write-Host "Starting deployment to dev environment..." -ForegroundColor Green
Write-Host "Source Dir: $SourceDir"
Write-Host "Target Dir: $TargetDir"
Write-Host ""

# Create target dir if not exists
if (-not (Test-Path $TargetDir)) {
    Write-Host "Creating target directory..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null
}

# Exclude Dirs and Files
$ExcludeDirs = @('.git', '.vscode', '.idea', '__pycache__', 'dist', 'test')
$ExcludeFiles = @('*.pyc', '.gitignore', 'dev_deploy.ps1', 'build_package.py', '.DS_Store', 'checklist.md')

# Clean Target Dir (Preserve Folder Structure? Actually code below removes recursive)
Write-Host "Cleaning target directory..." -ForegroundColor Yellow
if (Test-Path $TargetDir) {
    # 只删除文件和文件夹，保留目标根目录
    Get-ChildItem -Path $TargetDir -Recurse | Remove-Item -Force -Recurse -ErrorAction SilentlyContinue
}

# 复制文件函数
function Copy-ProjectFiles {
    param (
        [string]$Source,
        [string]$Destination
    )
    
    Get-ChildItem -Path $Source -Recurse | ForEach-Object {
        $relativePath = $_.FullName.Substring($Source.Length + 1)
        
        # Check Exclude Dirs
        $shouldExclude = $false
        foreach ($excludeDir in $ExcludeDirs) {
            # 简单的排除逻辑：如果相对路径以此开头，或者等于它
            if ($relativePath.StartsWith($excludeDir + "\") -or $relativePath -eq $excludeDir) {
                $shouldExclude = $true
                break
            }
        }
        
        # Check Exclude Files
        if (-not $shouldExclude) {
            foreach ($excludeFile in $ExcludeFiles) {
                if ($_.Name -like $excludeFile) {
                    $shouldExclude = $true
                    break
                }
            }
        }
        
        if (-not $shouldExclude) {
            $targetPath = Join-Path -Path $Destination -ChildPath $relativePath
            
            if ($_.PSIsContainer) {
                # Create Directory
                if (-not (Test-Path $targetPath)) {
                    New-Item -ItemType Directory -Path $targetPath -Force | Out-Null
                }
            } else {
                # Copy File
                $targetParent = Split-Path -Path $targetPath -Parent
                if (-not (Test-Path $targetParent)) {
                    New-Item -ItemType Directory -Path $targetParent -Force | Out-Null
                }
                Copy-Item -Path $_.FullName -Destination $targetPath -Force
                Write-Host "  Copy: $relativePath" -ForegroundColor Gray
            }
        }
    }
}

# Exec Copy
Write-Host "Copying files..." -ForegroundColor Yellow
Copy-ProjectFiles -Source $SourceDir -Destination $TargetDir

Write-Host ""
Write-Host "Deployment Complete!" -ForegroundColor Green
Write-Host "Target Dir: $TargetDir"
Write-Host ""
Write-Host "Tip: Restart Kodi or Reload Addons to see changes." -ForegroundColor Cyan

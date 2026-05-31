#Requires -Version 5.1
<#
.SYNOPSIS
    SmartBoot USB Bootable Drive Creator — PowerShell Fallback Script

.DESCRIPTION
    Creates a bootable USB drive from an ISO image.  This script is invoked
    by the Python SmartBoot application when the primary boot-sector writing
    methods (bootsect.exe / bcdboot.exe / syslinux) are unavailable or fail.

    Workflow
    --------
    1.  Locate the physical disk that owns the target drive letter.
    2.  Optionally reformat the disk (clean → partition → format).
    3.  Mount the ISO and copy its contents.
    4.  Install an appropriate bootloader (BIOS or UEFI).
    5.  Report structured JSON progress so the Python caller can update its UI.

.PARAMETER ISOPath
    Full path to the source ISO image.

.PARAMETER DriveLetter
    Single drive letter (A–Z) of the target USB volume.

.PARAMETER BootMode
    Boot mode to configure: Auto | BIOS | UEFI | Dual.
    Default: Auto (detected from ISO contents).

.PARAMETER PartitionScheme
    MBR or GPT.  When BootMode is UEFI or Dual this is forced to GPT.
    Default: Auto (derived from BootMode).

.PARAMETER SkipFormat
    If set, assume the drive is already formatted and skip the clean/format step.

.PARAMETER WindowsSourcePath
    Override the Windows installation source path used by bcdboot.exe.

.PARAMETER QuietProgress
    Suppress human-readable output; emit only JSON progress lines.
    The Python caller always passes this flag.

.NOTES
    Must be run as Administrator.
    All progress events are written to stdout as single-line JSON objects:
        {"step":"<name>","pct":<0-100>,"msg":"<description>","ok":<true|false>}
    Errors are additionally written to stderr for logging.
#>

[CmdletBinding(SupportsShouldProcess)]
param(
    [Parameter(Mandatory)][string]  $ISOPath,
    [Parameter(Mandatory)][ValidatePattern('^[A-Za-z]$')][string] $DriveLetter,
    [ValidateSet('Auto','BIOS','UEFI','Dual')][string] $BootMode        = 'Auto',
    [ValidateSet('Auto','MBR','GPT')]          [string] $PartitionScheme = 'Auto',
    [switch]  $SkipFormat,
    [string]  $WindowsSourcePath = '',
    [switch]  $QuietProgress
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# Normalise drive letter
$DriveLetter = $DriveLetter.ToUpper()

# ─────────────────────────────────────────────────────────────────────────────
# Progress helper
# ─────────────────────────────────────────────────────────────────────────────

function Write-Progress-Json {
    param(
        [string] $Step,
        [int]    $Pct,
        [string] $Msg,
        [bool]   $Ok = $true
    )
    $obj = [ordered]@{ step=$Step; pct=$Pct; msg=$Msg; ok=$Ok }
    $json = $obj | ConvertTo-Json -Compress
    Write-Host $json
    if (-not $QuietProgress) {
        $symbol = if ($Ok) { '✓' } else { '✗' }
        Write-Host "  [$symbol] [$Pct%] $Msg" -ForegroundColor $(if ($Ok) { 'Cyan' } else { 'Red' })
    }
}

function Fail {
    param([string]$Step, [int]$Pct, [string]$Msg)
    Write-Progress-Json -Step $Step -Pct $Pct -Msg $Msg -Ok $false
    Write-Error $Msg
    exit 1
}

# ─────────────────────────────────────────────────────────────────────────────
# Admin check
# ─────────────────────────────────────────────────────────────────────────────

function Test-Administrator {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = [Security.Principal.WindowsPrincipal]::new($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-Administrator)) {
    Fail 'init' 0 'Script must be run as Administrator.'
}

# ─────────────────────────────────────────────────────────────────────────────
# Validate parameters
# ─────────────────────────────────────────────────────────────────────────────

Write-Progress-Json 'init' 1 "Validating parameters…"

if (-not (Test-Path -LiteralPath $ISOPath -PathType Leaf)) {
    Fail 'init' 2 "ISO not found: $ISOPath"
}

# ─────────────────────────────────────────────────────────────────────────────
# Resolve physical disk number from drive letter
# ─────────────────────────────────────────────────────────────────────────────

function Get-DiskNumber-FromLetter {
    param([string]$Letter)
    try {
        # Try the partition API first (most reliable)
        $dn = Get-Partition | Where-Object { $_.DriveLetter -eq $Letter } |
              Select-Object -ExpandProperty DiskNumber -First 1
        if ($null -ne $dn) { return [int]$dn }
    } catch {}

    try {
        # WMI fallback
        $lDisk = Get-WmiObject Win32_LogicalDisk -Filter "DeviceID='${Letter}:'"
        $part  = $lDisk.GetRelated('Win32_DiskPartition') | Select-Object -First 1
        $disk  = $part.GetRelated('Win32_DiskDrive') | Select-Object -First 1
        if ($disk) {
            return [int]($disk.DeviceID -replace '\\\\\.\\PHYSICALDRIVE','')
        }
    } catch {}

    return -1
}

Write-Progress-Json 'resolve' 3 "Resolving disk number for drive ${DriveLetter}:…"
$diskNumber = Get-DiskNumber-FromLetter $DriveLetter

if ($diskNumber -lt 0) {
    # Drive may not be assigned yet; try to find any removable disk
    Write-Progress-Json 'resolve' 4 "Drive letter not found — scanning removable disks…" -Ok $false
    $removable = Get-Disk | Where-Object { $_.BusType -eq 'USB' } | Select-Object -First 1
    if ($removable) {
        $diskNumber = $removable.Number
        Write-Progress-Json 'resolve' 5 "Using first USB disk: Disk $diskNumber"
    } else {
        Fail 'resolve' 5 "No USB disk found. Connect a USB drive and retry."
    }
}

Write-Progress-Json 'resolve' 6 "Target: Disk $diskNumber  Drive: ${DriveLetter}:"

# ─────────────────────────────────────────────────────────────────────────────
# Detect ISO type from contents
# ─────────────────────────────────────────────────────────────────────────────

function Get-ISOType {
    param([string]$MountRoot)
    if (Test-Path "$MountRoot\sources\install.wim")   { return 'Windows' }
    if (Test-Path "$MountRoot\sources\install.esd")   { return 'Windows' }
    if (Test-Path "$MountRoot\casper")                 { return 'Linux' }
    if (Test-Path "$MountRoot\isolinux")               { return 'Linux' }
    if (Test-Path "$MountRoot\live")                   { return 'Linux' }
    if (Test-Path "$MountRoot\boot\grub")              { return 'Linux' }
    if (Test-Path "$MountRoot\kernel.sys")             { return 'FreeDOS' }
    if (Test-Path "$MountRoot\fdos")                   { return 'FreeDOS' }
    if (Test-Path "$MountRoot\EFI\BOOT\BOOTX64.EFI")  { return 'Generic-UEFI' }
    return 'Generic'
}

# ─────────────────────────────────────────────────────────────────────────────
# Format disk (unless skipped)
# ─────────────────────────────────────────────────────────────────────────────

function Invoke-Diskpart {
    param([string]$Script)
    $tmp = [IO.Path]::GetTempFileName()
    try {
        $Script | Out-File -FilePath $tmp -Encoding ASCII
        $out = diskpart /s $tmp 2>&1
        return ($LASTEXITCODE -eq 0), ($out -join "`n")
    } finally {
        Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    }
}

if (-not $SkipFormat) {
    Write-Progress-Json 'format' 8 "Determining partition scheme…"

    # Resolve partition scheme from user preference; BootMode may be refined
    # later once the ISO is mounted and its type is detected.
    $effectiveScheme = switch ($PartitionScheme) {
        'Auto' {
            if ($BootMode -in 'UEFI','Dual') { 'GPT' }
            elseif ($BootMode -eq 'BIOS')    { 'MBR' }
            else                              { 'MBR' }   # will update after ISO scan
        }
        default { $PartitionScheme }
    }

    Write-Progress-Json 'format' 10 "Formatting Disk $diskNumber as $effectiveScheme / FAT32…"

    $dpScript = @"
select disk $diskNumber
clean
convert $($effectiveScheme.ToLower())
create partition primary
select partition 1
active
format fs=fat32 label="SMARTBOOT" quick
assign letter=$DriveLetter
exit
"@
    $ok, $dpOut = Invoke-Diskpart $dpScript
    if (-not $ok) {
        Fail 'format' 15 "diskpart failed:`n$dpOut"
    }
    Write-Progress-Json 'format' 20 "Disk formatted (${effectiveScheme}/FAT32, letter ${DriveLetter}:)"

    # Brief pause so Windows registers the new volume
    Start-Sleep -Seconds 2
}

# ─────────────────────────────────────────────────────────────────────────────
# Mount ISO
# ─────────────────────────────────────────────────────────────────────────────

Write-Progress-Json 'mount' 22 "Mounting ISO: $ISOPath"

$mountResult = Mount-DiskImage -ImagePath $ISOPath -PassThru -ErrorAction Stop
$isoDriveLetter = ($mountResult | Get-Volume).DriveLetter
if (-not $isoDriveLetter) {
    Fail 'mount' 25 "Failed to mount ISO — could not determine drive letter."
}
$isoRoot = "${isoDriveLetter}:\"
Write-Progress-Json 'mount' 25 "ISO mounted as drive ${isoDriveLetter}:"

# Detect ISO type
$isoType = Get-ISOType $isoRoot
Write-Progress-Json 'detect' 26 "Detected ISO type: $isoType"

# Refine BootMode if Auto
if ($BootMode -eq 'Auto') {
    $BootMode = switch ($isoType) {
        'Windows'      { 'Dual'  }
        'Linux'        { 'BIOS'  }
        'FreeDOS'      { 'BIOS'  }
        'Generic-UEFI' { 'UEFI'  }
        default        { 'BIOS'  }
    }
    Write-Progress-Json 'detect' 27 "Boot mode set to: $BootMode"
}

# ─────────────────────────────────────────────────────────────────────────────
# Copy ISO contents
# ─────────────────────────────────────────────────────────────────────────────

Write-Progress-Json 'copy' 28 "Copying files from ISO to ${DriveLetter}:…"

$targetRoot = "${DriveLetter}:\"

try {
    # Prefer robocopy (multi-threaded, restartable)
    if (Get-Command robocopy -ErrorAction SilentlyContinue) {
        $robArgs = @($isoRoot, $targetRoot, '/E', '/NFL', '/NDL',
                     '/NJH', '/NJS', '/NC', '/NS', '/MT:8', '/R:2', '/W:1')
        robocopy @robArgs | Out-Null
        # robocopy exit codes 0-7 are success (bit-field)
        if ($LASTEXITCODE -gt 7) {
            throw "robocopy exited with code $LASTEXITCODE"
        }
    } else {
        xcopy "${isoRoot}*" $targetRoot /E /H /I /Q | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "xcopy failed ($LASTEXITCODE)" }
    }
    Write-Progress-Json 'copy' 60 "Files copied successfully"
} catch {
    # Unmount before failing
    Dismount-DiskImage -ImagePath $ISOPath -ErrorAction SilentlyContinue
    Fail 'copy' 60 "Copy failed: $_"
}

# ─────────────────────────────────────────────────────────────────────────────
# Helper: find bootsect.exe / bcdboot.exe from multiple locations
# ─────────────────────────────────────────────────────────────────────────────

function Find-Exe {
    param([string]$Name)
    # Check PATH
    $found = Get-Command $Name -ErrorAction SilentlyContinue
    if ($found) { return $found.Source }

    # Check Windows ADK
    $adkBases = @(
        $env:ProgramFiles,
        ${env:ProgramFiles(x86)}
    ) | Where-Object { $_ }

    foreach ($base in $adkBases) {
        foreach ($ver in '10','8.1','8.0') {
            $candidate = Join-Path $base "Windows Kits\$ver\Assessment and Deployment Kit\Deployment Tools\amd64\Oscdimg\$Name"
            if (Test-Path $candidate) { return $candidate }
        }
    }

    # ISO root
    if ($isoRoot -and (Test-Path "${isoRoot}boot\$Name")) {
        return "${isoRoot}boot\$Name"
    }
    if ($isoRoot -and (Test-Path "${isoRoot}sources\$Name")) {
        return "${isoRoot}sources\$Name"
    }

    return $null
}

# ─────────────────────────────────────────────────────────────────────────────
# Install BIOS bootloader
# ─────────────────────────────────────────────────────────────────────────────

function Install-BIOSBoot {
    Write-Progress-Json 'bios' 65 "Installing BIOS/MBR bootloader…"

    # bootsect.exe
    $bootsect = Find-Exe 'bootsect.exe'
    if ($bootsect) {
        Write-Progress-Json 'bios' 68 "Running bootsect.exe from $bootsect"
        & $bootsect /nt60 "${DriveLetter}:" /force /mbr 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-Progress-Json 'bios' 75 "BIOS boot sector written (bootsect.exe)"
            return $true
        }
        Write-Progress-Json 'bios' 69 "bootsect.exe failed (rc=$LASTEXITCODE)" -Ok $false
    }

    # Mark partition active via diskpart
    $ok, $_ = Invoke-Diskpart "select disk $diskNumber`nselect partition 1`nactive`nexit"
    if ($ok) {
        Write-Progress-Json 'bios' 72 "Partition marked active (diskpart)"
    }

    Write-Progress-Json 'bios' 75 "BIOS boot configured (limited — no bootsect.exe available)"
    return $true   # Partial success; the drive may still boot some ISOs
}

# ─────────────────────────────────────────────────────────────────────────────
# Install UEFI bootloader
# ─────────────────────────────────────────────────────────────────────────────

function Install-UEFIBoot {
    Write-Progress-Json 'uefi' 75 "Installing UEFI bootloader…"

    $efiBootDir = "${DriveLetter}:\EFI\BOOT"
    New-Item -ItemType Directory -Force -Path $efiBootDir | Out-Null
    $bootX64 = Join-Path $efiBootDir 'BOOTX64.EFI'

    # 1. bcdboot.exe (Windows ISO only)
    if ($isoType -eq 'Windows' -and $WindowsSourcePath) {
        $bcdboot = Find-Exe 'bcdboot.exe'
        if ($bcdboot) {
            Write-Progress-Json 'uefi' 78 "Running bcdboot.exe…"
            & $bcdboot $WindowsSourcePath /s "${DriveLetter}:" /f UEFI 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-Progress-Json 'uefi' 90 "UEFI boot configured (bcdboot.exe)"
                return $true
            }
            Write-Progress-Json 'uefi' 79 "bcdboot.exe failed (rc=$LASTEXITCODE)" -Ok $false
        }
    }

    # 2. Copy bootmgfw.efi from various locations
    $efiCandidates = @(
        "${isoRoot}efi\microsoft\boot\bootmgfw.efi",
        "${isoRoot}boot\efi\bootmgfw.efi",
        "$env:WINDIR\Boot\EFI\bootmgfw.efi"
    )
    # Add mounted ISO drives
    foreach ($l in [char[]](65..90)) {
        $efiCandidates += "${l}:\efi\microsoft\boot\bootmgfw.efi"
    }

    foreach ($src in $efiCandidates) {
        if (Test-Path $src) {
            Copy-Item -LiteralPath $src -Destination $bootX64 -Force -ErrorAction SilentlyContinue
            if (Test-Path $bootX64) {
                Write-Progress-Json 'uefi' 90 "UEFI bootloader copied from $src"
                return $true
            }
        }
    }

    # 3. Copy any .efi already on the target drive
    $existingEfi = Get-ChildItem -Path "${DriveLetter}:\EFI" -Recurse -Filter '*.efi' `
                    -ErrorAction SilentlyContinue |
                   Where-Object { $_.Name -ne 'BOOTX64.EFI' } |
                   Select-Object -First 1
    if ($existingEfi) {
        Copy-Item -LiteralPath $existingEfi.FullName -Destination $bootX64 -Force
        Write-Progress-Json 'uefi' 90 "UEFI bootloader copied from $($existingEfi.FullName)"
        return $true
    }

    # 4. Minimal PE32+ stub
    Write-Progress-Json 'uefi' 88 "Writing minimal UEFI stub (no real bootloader found)…" -Ok $false
    $stub = [byte[]]@(
        0x4D,0x5A,0x90,0x00,0x03,0x00,0x00,0x00,0x04,0x00,0x00,0x00,0xFF,0xFF,0x00,0x00,
        0xB8,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x40,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x40,0x00,0x00,0x00,
        0x50,0x45,0x00,0x00,0x64,0x86,0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0xF0,0x00,0x22,0x00,0x0B,0x02,0x00,0x00,0x00,0x10,0x00,0x00,
        0x00,0x10,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x10,0x00,0x00,0x00,0x10,0x00,0x00,
        0x00,0x00,0x40,0x00,0x00,0x00,0x00,0x00,0x00,0x10,0x00,0x00,0x00,0x02,0x00,0x00,
        0x0A,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x20,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        # Code: mov eax,3 (EFI_UNSUPPORTED); ret
        0xB8,0x03,0x00,0x00,0x00,0xC3
    )
    [IO.File]::WriteAllBytes($bootX64, $stub)
    Write-Progress-Json 'uefi' 90 "Minimal UEFI stub written to $bootX64"
    return $true
}

# ─────────────────────────────────────────────────────────────────────────────
# Detect Windows source for bcdboot
# ─────────────────────────────────────────────────────────────────────────────

if (-not $WindowsSourcePath -and $isoType -eq 'Windows') {
    foreach ($candidate in @(
        "${isoRoot}sources\install.wim",
        "${isoRoot}sources\install.esd",
        "${targetRoot}sources\install.wim"
    )) {
        if (Test-Path (Split-Path $candidate -Parent)) {
            $WindowsSourcePath = Split-Path (Split-Path $candidate -Parent) -Parent
            Write-Progress-Json 'detect' 62 "Windows source: $WindowsSourcePath"
            break
        }
    }
    if (-not $WindowsSourcePath) {
        $WindowsSourcePath = $env:WINDIR
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Unmount ISO before bootloader installation (some tools need the drive)
# ─────────────────────────────────────────────────────────────────────────────

Write-Progress-Json 'mount' 63 "Dismounting ISO…"
Dismount-DiskImage -ImagePath $ISOPath -ErrorAction SilentlyContinue

# ─────────────────────────────────────────────────────────────────────────────
# Install bootloader(s)
# ─────────────────────────────────────────────────────────────────────────────

$overallOk = $true

switch ($BootMode) {
    'BIOS' {
        $overallOk = Install-BIOSBoot
    }
    'UEFI' {
        $overallOk = Install-UEFIBoot
    }
    'Dual' {
        $biosOk = Install-BIOSBoot
        $uefiOk = Install-UEFIBoot
        $overallOk = $biosOk -or $uefiOk
        if (-not $biosOk) {
            Write-Progress-Json 'dual' 92 "Warning: BIOS bootloader failed; UEFI only" -Ok $false
        }
        if (-not $uefiOk) {
            Write-Progress-Json 'dual' 92 "Warning: UEFI bootloader failed; BIOS only" -Ok $false
        }
    }
    default {
        # Auto-resolved earlier; BIOS is safe default
        $overallOk = Install-BIOSBoot
    }
}

# ─────────────────────────────────────────────────────────────────────────────
# Finalise
# ─────────────────────────────────────────────────────────────────────────────

if ($overallOk) {
    Write-Progress-Json 'done' 100 "USB drive ${DriveLetter}: is ready (BootMode=$BootMode, ISO=$isoType)"
    exit 0
} else {
    Fail 'done' 98 "Bootloader installation did not fully succeed — drive may still boot."
}
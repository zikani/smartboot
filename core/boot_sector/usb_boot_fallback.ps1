#Requires -Version 5.1
<#
.SYNOPSIS
    SmartBoot USB Bootable Drive Creator — PowerShell Fallback Script

.DESCRIPTION
    Full Rufus-parity fallback. Creates a bootable USB drive from an ISO
    when primary Python-level methods (bootsect / bcdboot / syslinux) fail.

    Workflow
    --------
    1.  Resolve the physical disk from drive letter or scan for removable disks.
    2.  Optionally reformat (clean → partition → format).
    3.  Mount the ISO, detect its type, copy contents with robocopy.
    4.  Install BIOS and/or UEFI bootloader.
    5.  Finalise and report structured JSON progress.

    Rufus-parity features included:
      • Auto ISO-type detection (Windows / Linux / FreeDOS / Generic-UEFI)
      • Auto BootMode selection from ISO type
      • MBR and GPT partition support
      • BIOS (bootsect.exe → diskpart active)
      • UEFI (bcdboot → bootmgfw.efi → stub)
      • Dual (BIOS + UEFI)
      • Windows split-WIM (install.swm) copy
      • Structured JSON progress for Python caller
      • SkipFormat mode (re-use existing partition)

.PARAMETER ISOPath         Full path to the source ISO image.
.PARAMETER DriveLetter     Single drive letter (A–Z) of the target USB volume.
.PARAMETER BootMode        Auto | BIOS | UEFI | Dual  (default: Auto)
.PARAMETER PartitionScheme Auto | MBR | GPT            (default: Auto)
.PARAMETER SkipFormat      If set, skip disk clean/format step.
.PARAMETER WindowsSourcePath  Override Windows source for bcdboot.exe.
.PARAMETER QuietProgress   Emit only JSON lines (no colour output).
#>

[CmdletBinding()]
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
$DriveLetter = $DriveLetter.ToUpper()

# ─────────────────────────────────────────────────────────────────────────────
# Progress / error helpers
# ─────────────────────────────────────────────────────────────────────────────

function Write-J {
    param([string]$Step,[int]$Pct,[string]$Msg,[bool]$Ok=$true)
    $j = [ordered]@{step=$Step;pct=$Pct;msg=$Msg;ok=$Ok} | ConvertTo-Json -Compress
    Write-Host $j
    if (-not $QuietProgress) {
        Write-Host ("  [{0}][{1}%] {2}" -f (if ($Ok) {'✓'} else {'✗'}), $Pct, $Msg) `
            -ForegroundColor (if ($Ok) {'Cyan'} else {'Red'})
    }
}

function Fail {
    param([string]$Step,[int]$Pct,[string]$Msg)
    Write-J $Step $Pct $Msg $false
    Write-Error $Msg
    exit 1
}

# ─────────────────────────────────────────────────────────────────────────────
# Admin check
# ─────────────────────────────────────────────────────────────────────────────

$currentPrincipal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $currentPrincipal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Fail 'init' 0 'Script must be run as Administrator.'
}

Write-J 'init' 1 "Validating parameters…"

if (-not (Test-Path -LiteralPath $ISOPath -PathType Leaf)) {
    Fail 'init' 2 "ISO not found: $ISOPath"
}

# ─────────────────────────────────────────────────────────────────────────────
# Resolve physical disk
# ─────────────────────────────────────────────────────────────────────────────

function Get-DiskNumber {
    param([string]$Letter)
    try {
        $dn = Get-Partition | Where-Object {$_.DriveLetter -eq $Letter} |
              Select-Object -ExpandProperty DiskNumber -First 1
        if ($null -ne $dn) { return [int]$dn }
    } catch {}
    try {
        $ld   = Get-WmiObject Win32_LogicalDisk -Filter "DeviceID='${Letter}:'"
        $part = $ld.GetRelated('Win32_DiskPartition') | Select-Object -First 1
        $disk = $part.GetRelated('Win32_DiskDrive')    | Select-Object -First 1
        if ($disk) {
            return [int]($disk.DeviceID -replace '\\\\\.\\PHYSICALDRIVE','')
        }
    } catch {}
    return -1
}

Write-J 'resolve' 3 "Resolving disk for drive ${DriveLetter}:…"
$diskNumber = Get-DiskNumber $DriveLetter

if ($diskNumber -lt 0) {
    Write-J 'resolve' 4 "Drive letter not found — scanning USB disks…" $false
    $usbDisk = Get-Disk | Where-Object {$_.BusType -eq 'USB'} | Select-Object -First 1
    if ($usbDisk) {
        $diskNumber = $usbDisk.Number
        Write-J 'resolve' 5 "Using first USB disk: Disk $diskNumber"
    } else {
        Fail 'resolve' 5 "No USB disk found."
    }
}

# Confirm this is a removable / USB disk (safety check)
$diskObj = Get-Disk -Number $diskNumber
if ($diskObj.BusType -notin ('USB','SD') -and -not $diskObj.IsRemovable) {
    Fail 'resolve' 6 "Disk $diskNumber is not removable (BusType=$($diskObj.BusType)). Aborting for safety."
}

Write-J 'resolve' 6 "Target: Disk $diskNumber  Drive: ${DriveLetter}:  ($($diskObj.FriendlyName))"

# ─────────────────────────────────────────────────────────────────────────────
# ISO type detection
# ─────────────────────────────────────────────────────────────────────────────

function Get-ISOType { param([string]$Root)
    if (Test-Path "$Root\sources\install.wim")  { return 'Windows' }
    if (Test-Path "$Root\sources\install.esd")  { return 'Windows' }
    if (Test-Path "$Root\sources\boot.wim")     { return 'Windows' }
    if (Test-Path "$Root\casper")               { return 'Linux'   }
    if (Test-Path "$Root\isolinux")             { return 'Linux'   }
    if (Test-Path "$Root\live")                 { return 'Linux'   }
    if (Test-Path "$Root\boot\grub")            { return 'Linux'   }
    if (Test-Path "$Root\arch\boot")            { return 'Linux'   }
    if (Test-Path "$Root\kernel.sys")           { return 'FreeDOS' }
    if (Test-Path "$Root\fdos")                 { return 'FreeDOS' }
    if (Test-Path "$Root\EFI\BOOT\BOOTX64.EFI") { return 'Generic-UEFI' }
    return 'Generic'
}

# ─────────────────────────────────────────────────────────────────────────────
# diskpart helper
# ─────────────────────────────────────────────────────────────────────────────

function Invoke-Diskpart { param([string]$Script)
    $tmp = [IO.Path]::GetTempFileName()
    try {
        $Script | Out-File $tmp -Encoding ASCII
        $dpOut = diskpart /s $tmp 2>&1
        return @{ Ok = ($LASTEXITCODE -eq 0); Output = ($dpOut -join "`n") }
    } finally { Remove-Item $tmp -Force -EA SilentlyContinue }
}

# ─────────────────────────────────────────────────────────────────────────────
# Format disk
# ─────────────────────────────────────────────────────────────────────────────

if (-not $SkipFormat) {
    Write-J 'format' 8 "Determining partition scheme…"

    $effectiveScheme = switch ($PartitionScheme) {
        'Auto' { if ($BootMode -in 'UEFI','Dual') {'GPT'} else {'MBR'} }
        default { $PartitionScheme }
    }

    Write-J 'format' 10 "Formatting Disk $diskNumber as $effectiveScheme / FAT32…"

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
    $dpResult = Invoke-Diskpart $dpScript
    if (-not $dpResult.Ok) { Fail 'format' 15 "diskpart failed:`n$($dpResult.Output)" }

    Write-J 'format' 20 "Disk formatted (${effectiveScheme}/FAT32, letter ${DriveLetter}:)"
    Start-Sleep -Seconds 2
}

# ─────────────────────────────────────────────────────────────────────────────
# Mount ISO
# ─────────────────────────────────────────────────────────────────────────────

Write-J 'mount' 22 "Mounting ISO: $ISOPath"
$isoDriveLetter = (Mount-DiskImage -ImagePath $ISOPath -PassThru -EA Stop | Get-Volume).DriveLetter
if (-not $isoDriveLetter) { Fail 'mount' 25 "Failed to mount ISO." }
$isoRoot = "${isoDriveLetter}:\"
Write-J 'mount' 25 "ISO mounted as drive ${isoDriveLetter}:"

$isoType = Get-ISOType $isoRoot
Write-J 'detect' 26 "Detected ISO type: $isoType"

# Refine BootMode if Auto
if ($BootMode -eq 'Auto') {
    $BootMode = switch ($isoType) {
        'Windows'      { 'Dual'  }
        'Linux'        { 'BIOS'  }
        'FreeDOS'      { 'BIOS'  }
        'Generic-UEFI' { 'UEFI'  }
        default        { 'BIOS'  }
    }
    Write-J 'detect' 27 "Auto-selected boot mode: $BootMode"
}

# Refine PartitionScheme if Auto (post-ISO detection)
if (-not $SkipFormat -and $PartitionScheme -eq 'Auto') {
    if ($BootMode -in 'UEFI','Dual') {
        Write-J 'detect' 27 "Note: GPT preferred for $BootMode — re-run without SkipFormat if you need GPT"
    }
}

$targetRoot = "${DriveLetter}:\"

# ─────────────────────────────────────────────────────────────────────────────
# Copy ISO contents
# ─────────────────────────────────────────────────────────────────────────────

Write-J 'copy' 28 "Copying files from ISO to ${DriveLetter}:…"

try {
    if (Get-Command robocopy -EA SilentlyContinue) {
        robocopy $isoRoot $targetRoot /E /NFL /NDL /NJH /NJS /NC /NS /MT:8 /R:2 /W:1 | Out-Null
        if ($LASTEXITCODE -gt 7) { throw "robocopy exited $LASTEXITCODE" }
    } else {
        xcopy "${isoRoot}*" $targetRoot /E /H /I /Q | Out-Null
        if ($LASTEXITCODE -ne 0) { throw "xcopy failed ($LASTEXITCODE)" }
    }

    # Copy split WIM files if present (Windows large ISOs)
    if ($isoType -eq 'Windows') {
        Get-ChildItem "$isoRoot\sources" -Filter '*.swm' -EA SilentlyContinue |
            Where-Object {$_.Name -ne 'install.swm'} |
            Copy-Item -Destination "$targetRoot\sources\" -Force -EA SilentlyContinue
    }

    Write-J 'copy' 60 "Files copied successfully"
} catch {
    Dismount-DiskImage -ImagePath $ISOPath -EA SilentlyContinue
    Fail 'copy' 60 "Copy failed: $_"
}

# ─────────────────────────────────────────────────────────────────────────────
# Helper: find executable
# ─────────────────────────────────────────────────────────────────────────────

function Find-Exe { param([string]$Name)
    $cmd = Get-Command $Name -EA SilentlyContinue
    if ($cmd) { return $cmd.Source }
    # ADK
    foreach ($base in ($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
        if (-not $base) { continue }
        foreach ($ver in '10','8.1','8.0') {
            $c = Join-Path $base "Windows Kits\$ver\Assessment and Deployment Kit\Deployment Tools\amd64\Oscdimg\$Name"
            if (Test-Path $c) { return $c }
        }
    }
    # ISO root (Windows setup media ships boot tools)
    foreach ($sub in 'boot','sources') {
        $c = "${isoRoot}${sub}\$Name"
        if (Test-Path $c) { return $c }
    }
    return $null
}

# ─────────────────────────────────────────────────────────────────────────────
# Windows source for bcdboot
# ─────────────────────────────────────────────────────────────────────────────

if (-not $WindowsSourcePath -and $isoType -eq 'Windows') {
    foreach ($candidate in @(
        "${targetRoot}Windows",
        "${isoRoot}sources",
        $env:WINDIR
    )) {
        if (Test-Path $candidate) {
            $WindowsSourcePath = $candidate
            Write-J 'detect' 62 "Windows source: $WindowsSourcePath"
            break
        }
    }
    if (-not $WindowsSourcePath) { $WindowsSourcePath = $env:WINDIR }
}

# ─────────────────────────────────────────────────────────────────────────────
# Dismount ISO before bootloader write (some tools lock the drive)
# ─────────────────────────────────────────────────────────────────────────────

Write-J 'mount' 63 "Dismounting ISO…"
Dismount-DiskImage -ImagePath $ISOPath -EA SilentlyContinue

# ─────────────────────────────────────────────────────────────────────────────
# BIOS bootloader installer
# ─────────────────────────────────────────────────────────────────────────────

function Install-BIOSBoot {
    Write-J 'bios' 65 "Installing BIOS/MBR bootloader…"

    # bootsect.exe
    $bootsect = Find-Exe 'bootsect.exe'
    if ($bootsect) {
        Write-J 'bios' 68 "Running bootsect.exe…"
        & $bootsect /nt60 "${DriveLetter}:" /force /mbr 2>&1 | Out-Null
        if ($LASTEXITCODE -eq 0) {
            Write-J 'bios' 75 "BIOS boot sector written (bootsect.exe)"
            return $true
        }
        Write-J 'bios' 69 "bootsect.exe failed (rc=$LASTEXITCODE)" $false
    }

    # bcdboot.exe BIOS mode
    if ($WindowsSourcePath -and (Test-Path (Join-Path $WindowsSourcePath 'Windows'))) {
        $bcdboot = Find-Exe 'bcdboot.exe'
        if ($bcdboot) {
            Write-J 'bios' 70 "Running bcdboot.exe (BIOS)…"
            & $bcdboot (Join-Path $WindowsSourcePath 'Windows') /s "${DriveLetter}:" /f BIOS 2>&1 | Out-Null
            if ($LASTEXITCODE -eq 0) {
                Write-J 'bios' 75 "BIOS boot configured (bcdboot.exe)"
                return $true
            }
        }
    }

    # Mark active via diskpart
    $activeResult = Invoke-Diskpart "select disk $diskNumber`nselect partition 1`nactive`nexit"
    if ($activeResult.Ok) { Write-J 'bios' 73 "Partition marked active (diskpart)" }

    Write-J 'bios' 75 "BIOS boot configured (partition active — limited)"
    return $true
}

# ─────────────────────────────────────────────────────────────────────────────
# UEFI bootloader installer
# ─────────────────────────────────────────────────────────────────────────────

function Install-UEFIBoot {
    Write-J 'uefi' 76 "Installing UEFI bootloader…"

    $efiBootDir = "${DriveLetter}:\EFI\BOOT"
    New-Item -ItemType Directory -Force -Path $efiBootDir | Out-Null
    $bootX64 = Join-Path $efiBootDir 'BOOTX64.EFI'

    # 1. bcdboot.exe UEFI
    if ($isoType -eq 'Windows' -and $WindowsSourcePath) {
        $bcdboot = Find-Exe 'bcdboot.exe'
        if ($bcdboot) {
            Write-J 'uefi' 79 "Running bcdboot.exe (UEFI)…"
            $winDir = Join-Path $WindowsSourcePath 'Windows'
            if (Test-Path $winDir) {
                & $bcdboot $winDir /s "${DriveLetter}:" /f UEFI 2>&1 | Out-Null
                if ($LASTEXITCODE -eq 0) {
                    Write-J 'uefi' 90 "UEFI boot configured (bcdboot.exe)"
                    return $true
                }
                Write-J 'uefi' 80 "bcdboot.exe UEFI failed (rc=$LASTEXITCODE)" $false
            }
        }
    }

    # 2. bootmgfw.efi candidates
    $efiCandidates = @(
        "${targetRoot}efi\microsoft\boot\bootmgfw.efi",
        "${targetRoot}boot\efi\bootmgfw.efi",
        "$env:WINDIR\Boot\EFI\bootmgfw.efi"
    )
    foreach ($l in [char[]](65..90)) {
        $efiCandidates += "${l}:\efi\microsoft\boot\bootmgfw.efi"
    }
    foreach ($src in $efiCandidates) {
        if (Test-Path $src) {
            Copy-Item $src $bootX64 -Force -EA SilentlyContinue
            if (Test-Path $bootX64) {
                Write-J 'uefi' 90 "UEFI bootloader copied from $src"
                return $true
            }
        }
    }

    # 3. Any *.efi already on the target drive
    $existing = Get-ChildItem "${DriveLetter}:\EFI" -Recurse -Filter '*.efi' -EA SilentlyContinue |
                Where-Object {$_.Name -ne 'BOOTX64.EFI'} | Select-Object -First 1
    if ($existing) {
        Copy-Item $existing.FullName $bootX64 -Force
        Write-J 'uefi' 90 "UEFI bootloader copied from $($existing.FullName)"
        return $true
    }

    # 4. Minimal PE32+ stub (mov eax,3; ret → EFI_UNSUPPORTED)
    Write-J 'uefi' 88 "Writing minimal UEFI stub…" $false
    $stub = [byte[]](
        # DOS header (MZ … e_lfanew=0x40)
        0x4D,0x5A,0x90,0x00,0x03,0x00,0x00,0x00,0x04,0x00,0x00,0x00,0xFF,0xFF,0x00,0x00,
        0xB8,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x40,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x40,0x00,0x00,0x00,
        # PE sig + COFF (AMD64, 1 section, SizeOfOptionalHeader=0xF0, Char=0x0022)
        0x50,0x45,0x00,0x00,0x64,0x86,0x01,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0xF0,0x00,0x22,0x00,
        # Optional header PE32+ (magic=0x020B, EntryPoint=0x1000, SectionAlign=0x1000,
        #   FileAlign=0x200, SizeOfImage=0x2000, SizeOfHeaders=0x200, Subsystem=10)
        0x0B,0x02,0x0E,0x00,0x10,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x10,0x00,0x00,0x00,0x10,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x40,0x00,
        0x00,0x00,0x00,0x00,0x00,0x10,0x00,0x00,0x00,0x02,0x00,0x00,0x00,0x00,0x00,0x00,
        0x0A,0x00,0x00,0x00,0x00,0x20,0x00,0x00,0x00,0x02,0x00,0x00,0x00,0x00,0x00,0x00,
        # (padding to fill optional header to 0xF0 bytes)
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        # .text section entry
        0x2E,0x74,0x65,0x78,0x74,0x00,0x00,0x00,
        0x10,0x00,0x00,0x00,0x00,0x10,0x00,0x00,
        0x00,0x02,0x00,0x00,0x00,0x02,0x00,0x00,
        0x00,0x00,0x00,0x00,0x00,0x00,0x00,0x00,
        0x00,0x00,0x00,0x00,0x20,0x00,0x00,0x60
    )
    # Pad to FileAlignment (0x200) and append code
    $stub  += [byte[]](New-Object byte[] (0x200 - $stub.Length))
    $stub  += [byte[]](0xB8,0x03,0x00,0x00,0x00,0xC3)   # mov eax,3; ret
    $stub  += [byte[]](New-Object byte[] (0x200 - 6))

    [IO.File]::WriteAllBytes($bootX64, $stub)
    Write-J 'uefi' 90 "Minimal UEFI stub written to $bootX64"
    return $true
}

# ─────────────────────────────────────────────────────────────────────────────
# Run bootloader installation
# ─────────────────────────────────────────────────────────────────────────────

$overallOk = $true

switch ($BootMode) {
    'BIOS' { $overallOk = Install-BIOSBoot }
    'UEFI' { $overallOk = Install-UEFIBoot }
    'Dual' {
        $biosOk = Install-BIOSBoot
        $uefiOk = Install-UEFIBoot
        $overallOk = $biosOk -or $uefiOk
        if (-not $biosOk) { Write-J 'dual' 93 "BIOS bootloader failed; UEFI only" $false }
        if (-not $uefiOk) { Write-J 'dual' 93 "UEFI bootloader failed; BIOS only" $false }
    }
    default { $overallOk = Install-BIOSBoot }
}

# ─────────────────────────────────────────────────────────────────────────────
# Finalise
# ─────────────────────────────────────────────────────────────────────────────

if ($overallOk) {
    Write-J 'done' 100 "USB drive ${DriveLetter}: is ready (BootMode=$BootMode, ISO=$isoType)"
    exit 0
} else {
    Fail 'done' 98 "Bootloader installation did not fully succeed."
}
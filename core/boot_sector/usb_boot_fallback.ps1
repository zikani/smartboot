# USB Bootable Drive Creator using WMI - Fallback Method
# This script serves as a fallback when standard boot sector methods fail
# Run as Administrator

# Parameters
param(
    [Parameter(Mandatory=$true)]
    [string]$ISOPath,
    
    [Parameter(Mandatory=$true)]
    [string]$DriveLetter,
    
    [Parameter(Mandatory=$false)]
    [ValidateSet("Auto", "BIOS", "UEFI")]
    [string]$BootMode = "Auto",
    
    [Parameter(Mandatory=$false)]
    [string]$WindowsSourcePath = "C:\Windows"
)

function Write-Log {
    param([string]$Message)
    Write-Host "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $Message"
}

function Test-Administrator {
    $currentUser = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
    return $currentUser.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Format-USBDiskpart {
    param(
        [string]$DriveLetter,
        [ValidateSet("MBR", "GPT")]
        [string]$PartitionScheme = "MBR"
    )
    
    try {
        Write-Log "Formatting USB drive $DriveLetter using diskpart ($PartitionScheme)..."
        
        # Get the disk number from the drive letter
        $disk = Get-WmiObject -Class Win32_LogicalDisk -Filter "DeviceID='$($DriveLetter):'" | 
               Get-WmiObject -Query "ASSOCIATORS OF {Win32_LogicalDisk.DeviceID='$($DriveLetter):'} WHERE AssocClass=Win32_LogicalDiskToPartition" |
               Get-WmiObject -Query "ASSOCIATORS OF {Win32_DiskPartition.DeviceID='$($_.DeviceID)'} WHERE AssocClass=Win32_DiskDriveToDiskPartition"
        
        if (-not $disk) {
            Write-Log "Error: Could not find disk for drive $DriveLetter"
            return $false
        }
        
        # Extract disk number from DeviceID (typically in format \\.\PHYSICALDRIVE0)
        $diskNumber = ($disk.DeviceID -replace '\\\\\.\\PHYSICALDRIVE', '')
        
        # Create diskpart script based on partition scheme
        if ($PartitionScheme -eq "MBR") {
            $diskpartCommands = @"
list disk
select disk $diskNumber
clean
create partition primary
select partition 1
active
format fs=fat32 quick
assign letter=$DriveLetter
exit
"@
        } else {
            # GPT for UEFI
            $diskpartCommands = @"
list disk
select disk $diskNumber
clean
convert gpt
create partition primary
format fs=fat32 quick
assign letter=$DriveLetter
exit
"@
        }
        
        # Execute diskpart
        $tempFile = [System.IO.Path]::GetTempFileName()
        $diskpartCommands | Out-File -FilePath $tempFile -Encoding ASCII
        $diskpartOutput = diskpart /s $tempFile
        Remove-Item -Path $tempFile -Force
        
        # Check if successful
        if ($diskpartOutput -match "DiskPart successfully") {
            Write-Log "Drive formatted successfully using diskpart."
            return $true
        } else {
            Write-Log "Error formatting drive with diskpart. Output: $diskpartOutput"
            return $false
        }
    }
    catch {
        Write-Log "Error during diskpart formatting: $_"
        return $false
    }
}

function Copy-ISOContents {
    param(
        [string]$ISOPath,
        [string]$DriveLetter
    )
    
    try {
        Write-Log "Mounting ISO image $ISOPath..."
        
        # Mount the ISO file
        $mountResult = Mount-DiskImage -ImagePath $ISOPath -PassThru
        $isoDriveLetter = ($mountResult | Get-Volume).DriveLetter
        
        if (-not $isoDriveLetter) {
            Write-Log "Error: Failed to mount ISO image."
            return $false
        }
        
        Write-Log "ISO mounted as drive $isoDriveLetter"
        
        # Copy all files from ISO to USB drive
        Write-Log "Copying files from ISO to USB drive..."
        Copy-Item -Path "$($isoDriveLetter):\*" -Destination "$($DriveLetter):\" -Recurse -Force
        
        # Unmount the ISO
        Write-Log "Dismounting ISO image..."
        Dismount-DiskImage -ImagePath $ISOPath
        
        Write-Log "Files copied successfully."
        return $true
    }
    catch {
        Write-Log "Error copying ISO contents: $_"
        try {
            Dismount-DiskImage -ImagePath $ISOPath -ErrorAction SilentlyContinue
        }
        catch {}
        return $false
    }
}

function Install-Bootloader {
    param(
        [string]$DriveLetter,
        [string]$BootMode,
        [string]$WindowsSourcePath
    )
    
    try {
        Write-Log "Installing bootloader on drive $DriveLetter (Mode: $BootMode)..."
        
        # Determine boot mode if set to Auto
        if ($BootMode -eq "Auto") {
            $hasEFIFolder = Test-Path -Path "$($DriveLetter):\EFI"
            if ($hasEFIFolder) {
                $BootMode = "UEFI"
                Write-Log "Auto-detected UEFI boot mode."
            } else {
                $BootMode = "BIOS"
                Write-Log "Auto-detected BIOS boot mode."
            }
        }
        
        # Install appropriate bootloader
        if ($BootMode -eq "UEFI") {
            # Check if Windows source path exists
            if (-not (Test-Path $WindowsSourcePath)) {
                Write-Log "Error: Windows source path not found: $WindowsSourcePath"
                return $false
            }
            
            # Execute bcdboot for UEFI boot
            Write-Log "Installing UEFI bootloader using bcdboot..."
            $bcdbootResult = Start-Process -FilePath "bcdboot.exe" -ArgumentList "$WindowsSourcePath /s $($DriveLetter): /f UEFI" -Wait -PassThru -NoNewWindow
            
            if ($bcdbootResult.ExitCode -ne 0) {
                Write-Log "Warning: bcdboot.exe might have failed with exit code $($bcdbootResult.ExitCode)"
                
                # Check if the EFI directory structure exists
                if (-not (Test-Path "$($DriveLetter):\EFI\BOOT\bootx64.efi")) {
                    Write-Log "Critical: bootx64.efi not found. UEFI boot will likely fail."
                    return $false
                }
            }
        } else {
            # Execute bootsect for BIOS/MBR boot
            Write-Log "Installing BIOS/MBR bootloader using bootsect..."
            $bootsectPath = "$env:SystemRoot\system32\bootsect.exe"
            
            if (-not (Test-Path $bootsectPath)) {
                # If not found in system32, try Windows ADK path
                $adkPaths = @(
                    "${env:ProgramFiles(x86)}\Windows Kits\10\Assessment and Deployment Kit\Deployment Tools\amd64\Oscdimg\bootsect.exe",
                    "${env:ProgramFiles(x86)}\Windows Kits\10\Assessment and Deployment Kit\Deployment Tools\x86\Oscdimg\bootsect.exe",
                    "${env:ProgramFiles}\Windows Kits\10\Assessment and Deployment Kit\Deployment Tools\amd64\Oscdimg\bootsect.exe"
                )
                
                foreach ($path in $adkPaths) {
                    if (Test-Path $path) {
                        $bootsectPath = $path
                        break
                    }
                }
                
                if (-not (Test-Path $bootsectPath)) {
                    Write-Log "Error: bootsect.exe not found. Please ensure Windows ADK is installed."
                    return $false
                }
            }
            
            $bootsectResult = Start-Process -FilePath $bootsectPath -ArgumentList "/nt60 $($DriveLetter): /force /mbr" -Wait -PassThru -NoNewWindow
            
            if ($bootsectResult.ExitCode -ne 0) {
                Write-Log "Error: bootsect.exe failed with exit code $($bootsectResult.ExitCode)"
                return $false
            }
        }
        
        Write-Log "Bootloader installation completed successfully."
        return $true
    }
    catch {
        Write-Log "Error installing bootloader: $_"
        return $false
    }
}

function Get-WindowsSource {
    param(
        [string]$ISODriveLetter
    )
    
    $commonPaths = @(
        "$($ISODriveLetter):\sources\install.wim",
        "$($ISODriveLetter):\sources\install.esd",
        "$($ISODriveLetter):\Windows"
    )
    
    foreach ($path in $commonPaths) {
        if (Test-Path $path) {
            # Found a potential Windows source
            if ($path -like "*\sources\install.*") {
                # For WIM/ESD files, we need to return the root directory
                return (Split-Path (Split-Path $path -Parent) -Parent)
            } else {
                return $path
            }
        }
    }
    
    # Default to system Windows directory if ISO doesn't contain it
    return "C:\Windows"
}

# Main execution
try {
    # Check if running as administrator
    if (-not (Test-Administrator)) {
        Write-Log "This script requires administrator privileges. Please run as administrator."
        exit 1
    }
    
    # Validate parameters
    if (-not (Test-Path $ISOPath)) {
        Write-Log "Error: ISO file not found at path: $ISOPath"
        exit 1
    }
    
    if (-not $DriveLetter -match '^[A-Z]$') {
        Write-Log "Error: Drive letter should be a single character (A-Z)"
        exit 1
    }
    
    # Determine appropriate partition scheme based on boot mode
    $partitionScheme = "MBR"
    if ($BootMode -eq "UEFI") {
        $partitionScheme = "GPT"
    }
    
    # Format the USB drive using diskpart
    if (-not (Format-USBDiskpart -DriveLetter $DriveLetter -PartitionScheme $partitionScheme)) {
        Write-Log "Failed to format USB drive. Aborting."
        exit 1
    }
    
    # Copy contents from ISO to USB
    if (-not (Copy-ISOContents -ISOPath $ISOPath -DriveLetter $DriveLetter)) {
        Write-Log "Failed to copy ISO contents. Aborting."
        exit 1
    }
    
    # Try to detect Windows source path from ISO
    Write-Log "Mounting ISO to detect Windows source..."
    $mountResult = Mount-DiskImage -ImagePath $ISOPath -PassThru
    $isoDriveLetter = ($mountResult | Get-Volume).DriveLetter
    
    if ($isoDriveLetter) {
        $detectedWinSource = Get-WindowsSource -ISODriveLetter $isoDriveLetter
        if ($detectedWinSource -ne "C:\Windows") {
            $WindowsSourcePath = $detectedWinSource
            Write-Log "Detected Windows source path: $WindowsSourcePath"
        }
        Dismount-DiskImage -ImagePath $ISOPath
    }
    
    # Install bootloader
    if (-not (Install-Bootloader -DriveLetter $DriveLetter -BootMode $BootMode -WindowsSourcePath $WindowsSourcePath)) {
        Write-Log "Failed to install bootloader. USB drive may not be bootable."
    }
    
    Write-Log "USB drive preparation completed. Drive $DriveLetter should now be bootable."
    exit 0
}
catch {
    Write-Log "Critical error: $_"
    exit 1
}

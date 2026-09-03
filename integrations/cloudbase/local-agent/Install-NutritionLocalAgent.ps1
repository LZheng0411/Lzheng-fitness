[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$ConfigPath,
  [string]$RunnerPath=(Join-Path $PSScriptRoot 'Run-NutritionLocalAgent.ps1'),
  [ValidateSet('lzheng-fitness-agent')][string]$ProtocolName='lzheng-fitness-agent'
)

$ErrorActionPreference='Stop'
$resolvedConfig=(Resolve-Path -LiteralPath $ConfigPath).Path
$resolvedRunner=(Resolve-Path -LiteralPath $RunnerPath).Path
$handler=(Resolve-Path -LiteralPath (Join-Path $PSScriptRoot 'Invoke-NutritionLocalAgentProtocol.ps1')).Path
$protocolRoot="HKCU:\Software\Classes\$ProtocolName"
New-Item -Path $protocolRoot -Force|Out-Null
Set-Item -Path $protocolRoot -Value "URL:$ProtocolName Protocol"
New-ItemProperty -Path $protocolRoot -Name 'URL Protocol' -Value '' -PropertyType String -Force|Out-Null
New-ItemProperty -Path $protocolRoot -Name 'FitnessConfigPath' -Value $resolvedConfig -PropertyType String -Force|Out-Null
New-ItemProperty -Path $protocolRoot -Name 'FitnessRunnerPath' -Value $resolvedRunner -PropertyType String -Force|Out-Null
$command='"powershell.exe" -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{0}" -Uri "%1"' -f $handler
New-Item -Path (Join-Path $protocolRoot 'shell\open\command') -Force|Out-Null
Set-Item -Path (Join-Path $protocolRoot 'shell\open\command') -Value $command
Add-Type -Namespace Win32 -Name ShellRefresh -MemberDefinition '[DllImport("shell32.dll")] public static extern void SHChangeNotify(int eventId, uint flags, IntPtr item1, IntPtr item2);'
[Win32.ShellRefresh]::SHChangeNotify(0x08000000,0,[IntPtr]::Zero,[IntPtr]::Zero)
$visible=Get-Item -LiteralPath "Registry::HKEY_CLASSES_ROOT\$ProtocolName" -ErrorAction Stop
[ordered]@{mode='manual-on-demand-once';enabled=$true;automaticTriggers=0;protocol=$visible.PSChildName;configPath=$resolvedConfig;runnerPath=$resolvedRunner;startedByInstaller=$false}|ConvertTo-Json

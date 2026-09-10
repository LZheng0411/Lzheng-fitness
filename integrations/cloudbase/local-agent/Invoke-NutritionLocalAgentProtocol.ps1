[CmdletBinding()]
param(
  [Parameter(Mandatory=$true)][string]$Uri,
  [ValidateSet('lzheng-fitness-agent')][string]$ProtocolName='lzheng-fitness-agent'
)

$ErrorActionPreference='Stop'
$parsed=[Uri]$Uri
if($parsed.Scheme -ne $ProtocolName -or $parsed.Host -ne 'run'){throw 'unsupported_protocol_action'}
if($Uri -notmatch '^lzheng-fitness-agent://run/?(?:\?job=[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})?$'){throw 'unsupported_protocol_action'}
$protocolRoot="HKCU:\Software\Classes\$ProtocolName"
$config=(Get-ItemPropertyValue -LiteralPath $protocolRoot -Name 'FitnessConfigPath')
$runner=(Get-ItemPropertyValue -LiteralPath $protocolRoot -Name 'FitnessRunnerPath')
if((-not (Test-Path -LiteralPath $config -PathType Leaf)) -or (-not (Test-Path -LiteralPath $runner -PathType Leaf))){throw 'protocol_private_config_or_runner_missing'}
$launchArgs=@('-NoProfile','-ExecutionPolicy','Bypass','-File',('"'+$runner+'"'),'-Once','-ConfigPath',('"'+$config+'"'));if($parsed.Query){$launchArgs+=@('-JobId',$parsed.Query.Substring(5))};Start-Process -FilePath powershell.exe -WindowStyle Hidden -ArgumentList $launchArgs|Out-Null

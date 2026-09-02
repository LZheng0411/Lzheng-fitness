[CmdletBinding()]
param([string]$ProtocolName='lzheng-fitness-agent')

$root="HKCU:\Software\Classes\$ProtocolName"
$installed=Test-Path -LiteralPath $root
$config=$null;$runner=$null
if($installed){$config=Get-ItemPropertyValue -LiteralPath $root -Name 'FitnessConfigPath' -ErrorAction SilentlyContinue;$runner=Get-ItemPropertyValue -LiteralPath $root -Name 'FitnessRunnerPath' -ErrorAction SilentlyContinue}
[ordered]@{mode='manual-on-demand-once';protocolInstalled=$installed;configAvailable=[bool]($config -and (Test-Path -LiteralPath $config -PathType Leaf));runnerAvailable=[bool]($runner -and (Test-Path -LiteralPath $runner -PathType Leaf));automaticTriggers=0}|ConvertTo-Json

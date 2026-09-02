$ErrorActionPreference='Stop'
$root=Split-Path -Parent $MyInvocation.MyCommand.Path
$run=Get-Content -Raw (Join-Path $root 'Run-NutritionLocalAgent.ps1')
$install=Get-Content -Raw (Join-Path $root 'Install-NutritionLocalAgent.ps1')
$protocol=Get-Content -Raw (Join-Path $root 'Invoke-NutritionLocalAgentProtocol.ps1')
$errors=@()
if($run -notmatch '\$WatchHardLimitMinutes=10'){$errors+='missing 10 minute cap'}
if($run -notmatch '\$WatchHardEmptyLimit=3'){$errors+='missing 3 empty cap'}
if($run -notmatch '\$WatchHardFailureLimit=3'){$errors+='missing 3 failure cap'}
if($run -notmatch 'if \(-not \$Watch\) \{ Invoke-SerializedAgentCycle -RunMode ''once'''){$errors+='default is not once-only'}
if($run -notmatch 'Threading\.Mutex'){$errors+='missing cross-process queue mutex'}
if($run -match 'Invoke-WebRequest|curl|codex |openai|while\s*\(\s*\$true\s*\)'){$errors+='public runner has a network/model/infinite-loop path'}
if($install -match 'Register-ScheduledTask|New-ScheduledTaskTrigger|Start-ScheduledTask'){$errors+='installer registers or starts a task'}
if($protocol -notmatch "Host -ne 'run'"){$errors+='protocol does not restrict actions to explicit run'}
if($protocol -match 'Register-ScheduledTask|Start-ScheduledTask|setInterval|while\s*\('){$errors+='protocol adds an automatic or recurring trigger'}
if($install -notmatch 'SHChangeNotify' -or $install -notmatch 'HKEY_CLASSES_ROOT'){$errors+='protocol installer does not refresh and verify the registered handler'}
if($errors.Count){$errors|ForEach-Object{Write-Error $_};exit 1}
[ordered]@{passed=$true;mode='manual-on-demand-once';automaticTriggers=0;emptyQueueModelCalls=0;watchMaxMinutes=10;watchEmptyCircuit=3;watchFailureCircuit=3}|ConvertTo-Json

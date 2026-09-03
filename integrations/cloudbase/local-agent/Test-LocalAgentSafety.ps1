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
$template=Get-Content -Raw (Join-Path $root '../../../skills/lzheng-fitness-workbench-builder/assets/workbench-template.html')
if($template -notmatch "agentUri:'lzheng-fitness-agent://run'" -or $template -match 'lzheng-nutrition-agent://') { throw 'web protocol does not match the public installer' }
foreach($invalid in @('lzheng-fitness-agent://run?path=bad','lzheng-fitness-agent://run/extra','lzheng-fitness-agent://run#extra','lzheng-fitness-agent://run:123','lzheng-fitness-agent://user@run')) {
  $rejected=$false
  try { & (Join-Path $root 'Invoke-NutritionLocalAgentProtocol.ps1') -Uri $invalid } catch { $rejected=$_.Exception.Message -eq 'unsupported_protocol_action' }
  if(-not $rejected) { throw 'Protocol accepted URI data or reached private configuration' }
}
# Positive forwarding test with scoped mocks: never touch a real registration,
# launch a process, or read a user's private configuration.
& {
  $capture=[Collections.Generic.List[object]]::new()
  function Get-ItemPropertyValue { param($LiteralPath,$Name) return ('fixture with spaces/'+$Name+'.ps1') }
  function Test-Path { param($LiteralPath,$PathType) return $true }
  function Start-Process { param($FilePath,$WindowStyle,$ArgumentList) $capture.Add(@{file=$FilePath;style=$WindowStyle;args=$ArgumentList}) }
  & (Join-Path $root 'Invoke-NutritionLocalAgentProtocol.ps1') -Uri 'lzheng-fitness-agent://run'
  if($capture.Count -ne 1 -or $capture[0].style -ne 'Hidden') { throw 'Protocol must launch exactly one hidden process' }
  if($capture[0].args -notcontains '-Once' -or $capture[0].args -notcontains '"fixture with spaces/FitnessRunnerPath.ps1"' -or $capture[0].args -notcontains '"fixture with spaces/FitnessConfigPath.ps1"') { throw 'Protocol did not preserve quoted paths and once-only mode' }
}
[ordered]@{passed=$true;mode='manual-on-demand-once';automaticTriggers=0;emptyQueueModelCalls=0;watchMaxMinutes=10;watchEmptyCircuit=3;watchFailureCircuit=3}|ConvertTo-Json

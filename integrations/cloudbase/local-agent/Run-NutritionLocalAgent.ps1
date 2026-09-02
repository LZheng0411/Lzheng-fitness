[CmdletBinding()]
param([switch]$Once,[switch]$Watch,[string]$QueueFile,[string]$ConfigPath)

$ErrorActionPreference='Stop'
$WatchHardLimitMinutes=10; $WatchHardEmptyLimit=3; $WatchHardFailureLimit=3
function Read-JsonFile([string]$Path,[object]$Default){if((-not $Path) -or (-not (Test-Path -LiteralPath $Path))){return $Default};Get-Content -Raw -LiteralPath $Path|ConvertFrom-Json}
function Write-Queue([object[]]$Jobs){$Jobs|ConvertTo-Json -Depth 16|Set-Content -LiteralPath $QueueFile -Encoding UTF8}
function Test-Candidate([object]$Value,[string]$JobType){if(($null -eq $Value) -or ($Value -isnot [pscustomobject])){throw 'agent_result_must_be_an_object'};if($Value.confidence -eq $null-or (([double]$Value.confidence -lt 0) -or ([double]$Value.confidence -gt 1))){throw 'confidence_must_be_0_to_1'};if($JobType -in @('meal_analysis','meal_consumption_analysis')){if($Value.foods -isnot [array]){throw 'meal_candidate_requires_foods_array'}}elseif($JobType -eq 'weekly_review'){if($Value.recommendation -isnot [pscustomobject]){throw 'weekly_candidate_requires_recommendation_object'}}else{throw 'unsupported_job_type'}}
function Invoke-AgentCycle {
  param([string]$RunMode)
  if((-not $QueueFile) -and $ConfigPath){$earlyConfig=Read-JsonFile $ConfigPath $null;if($earlyConfig -and $earlyConfig.queue_file){$script:QueueFile=[string]$earlyConfig.queue_file}}
  $jobs=@(Read-JsonFile $QueueFile @());$job=@($jobs|Where-Object {$_.status -in @('queued','pending_agent')}|Select-Object -First 1)
  if($job.Count -eq 0){return @{state='empty';modelCalls=0}}
  $config=Read-JsonFile $ConfigPath $null;if(($null -eq $config) -or (-not $config.adapter_command)){return @{state='private_adapter_required';modelCalls=0;jobId=$job[0].id}}
  $target=$jobs|Where-Object {$_.id -eq $job[0].id}|Select-Object -First 1;if($target.status -notin @('queued','pending_agent')){return @{state='already_claimed';modelCalls=0;jobId=$target.id}}
  $target.status='processing';$target|Add-Member -NotePropertyName claimed_at -NotePropertyValue (Get-Date).ToUniversalTime().ToString('o') -Force;Write-Queue $jobs
  $temp=Join-Path ([IO.Path]::GetTempPath()) ('fitness-agent-'+$target.id);New-Item -ItemType Directory -Force -Path $temp|Out-Null
  try{$input=Join-Path $temp 'input.json';$output=Join-Path $temp 'output.json';$target.input_snapshot|ConvertTo-Json -Depth 16|Set-Content $input -Encoding UTF8;if([IO.Path]::GetExtension($config.adapter_command) -eq '.ps1'){$p=Start-Process -FilePath powershell -ArgumentList @('-NoProfile','-ExecutionPolicy','Bypass','-File',$config.adapter_command,$input,$output) -Wait -PassThru -NoNewWindow}else{$p=Start-Process -FilePath $config.adapter_command -ArgumentList @($input,$output) -Wait -PassThru -NoNewWindow};if(($p.ExitCode -ne 0) -or (-not (Test-Path -LiteralPath $output))){throw 'adapter_failed'};$candidate=Get-Content -Raw $output|ConvertFrom-Json;Test-Candidate $candidate $target.job_type;$target.status='completed';$target|Add-Member -NotePropertyName result -NotePropertyValue $candidate -Force;$target|Add-Member -NotePropertyName completed_at -NotePropertyValue (Get-Date).ToUniversalTime().ToString('o') -Force;Write-Queue $jobs;return @{state='completed';modelCalls=1;jobId=$target.id}}
  catch{$target.status='failed';$target|Add-Member -NotePropertyName error_message -NotePropertyValue $_.Exception.Message -Force;$target|Add-Member -NotePropertyName completed_at -NotePropertyValue (Get-Date).ToUniversalTime().ToString('o') -Force;Write-Queue $jobs;throw}
  finally{if(Test-Path -LiteralPath $temp){Remove-Item -LiteralPath $temp -Recurse -Force}}
}
function Invoke-SerializedAgentCycle([string]$RunMode){
  if(-not $QueueFile){return Invoke-AgentCycle -RunMode $RunMode}
  $bytes=[Text.Encoding]::UTF8.GetBytes(([IO.Path]::GetFullPath($QueueFile).ToLowerInvariant()));$sha=[Security.Cryptography.SHA256]::Create();try{$hash=$sha.ComputeHash($bytes)}finally{$sha.Dispose()};$name='Global\LzhengFitnessQueue-'+(([BitConverter]::ToString($hash)).Replace('-','').Substring(0,24));$mutex=[Threading.Mutex]::new($false,$name)
  try{if(-not $mutex.WaitOne(0)){return @{state='already_claimed';modelCalls=0}};return Invoke-AgentCycle -RunMode $RunMode}finally{try{$mutex.ReleaseMutex()}catch{};$mutex.Dispose()}
}
if (-not $Watch) { Invoke-SerializedAgentCycle -RunMode 'once' | ConvertTo-Json; exit 0 }
$started=Get-Date;$empty=0;$failures=0
while(((Get-Date)-$started).TotalMinutes -lt $WatchHardLimitMinutes){try{$result=Invoke-SerializedAgentCycle 'watch';if($result.state -eq 'empty'){$empty++;if($empty -ge $WatchHardEmptyLimit){break}}else{$empty=0};$failures=0}catch{$failures++;if($failures -ge $WatchHardFailureLimit){break}};Start-Sleep -Seconds 120}

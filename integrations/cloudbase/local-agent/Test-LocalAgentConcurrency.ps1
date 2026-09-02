$ErrorActionPreference='Stop'
$root=$PSScriptRoot;$run=Join-Path $root 'Run-NutritionLocalAgent.ps1';$temp=Join-Path ([IO.Path]::GetTempPath()) ('fitness-agent-concurrency-'+[guid]::NewGuid())
New-Item -ItemType Directory -Path $temp|Out-Null
try{
 $queue=Join-Path $temp 'queue.json';$config=Join-Path $temp 'config.json';$adapter=Join-Path $temp 'adapter.ps1';$counter=Join-Path $temp 'count.txt'
 @(@{id='job-one';job_type='meal_analysis';status='queued';input_snapshot=@{foods=@()}})|ConvertTo-Json -Depth 8|Set-Content $queue -Encoding UTF8
 @'
param($input,$output)
$counter=Join-Path $PSScriptRoot 'count.txt'
[IO.File]::AppendAllText($counter,"1`n")
Start-Sleep -Milliseconds 400
@{foods=@(@{name='test'});confidence=.8}|ConvertTo-Json -Depth 8|Set-Content $output -Encoding UTF8
'@|Set-Content $adapter -Encoding UTF8
 @{adapter_command=$adapter}|ConvertTo-Json|Set-Content $config -Encoding UTF8
 $arguments='-NoProfile -ExecutionPolicy Bypass -File "'+$run+'" -Once -QueueFile "'+$queue+'" -ConfigPath "'+$config+'"'
 function Start-AgentProcess($argumentLine){$psi=[Diagnostics.ProcessStartInfo]::new();$psi.FileName=(Get-Command powershell).Source;$psi.Arguments=$argumentLine;$psi.UseShellExecute=$false;$psi.RedirectStandardOutput=$true;$psi.RedirectStandardError=$true;$psi.CreateNoWindow=$true;$p=[Diagnostics.Process]::new();$p.StartInfo=$psi;[void]$p.Start();return $p}
 $a=Start-AgentProcess $arguments;$b=Start-AgentProcess $arguments;$a.WaitForExit();$b.WaitForExit();$aOut=$a.StandardOutput.ReadToEnd();$bOut=$b.StandardOutput.ReadToEnd();$aErr=$a.StandardError.ReadToEnd();$bErr=$b.StandardError.ReadToEnd();if($a.ExitCode -ne 0 -or $b.ExitCode -ne 0){throw ('agent process exit='+$a.ExitCode+','+$b.ExitCode+' '+$aErr+$bErr+$aOut+$bOut)}
 if((@($aOut,$bOut|Where-Object {$_ -match '"state"\s*:\s*"completed"'}).Count -ne 1) -or (@($aOut,$bOut|Where-Object {$_ -match '"state"\s*:\s*"already_claimed"'}).Count -ne 1)){throw 'expected one completed and one already_claimed process'}
 $count=@(Get-Content $counter).Count;if($count -ne 1){throw "adapter executed $count times"}
 $job=(Get-Content -Raw $queue|ConvertFrom-Json)[0];if($job.status -ne 'completed'){throw 'job did not complete'}
 $left=Get-ChildItem ([IO.Path]::GetTempPath()) -Filter 'fitness-agent-job-one*' -ErrorAction SilentlyContinue;if($left){throw 'temporary job directory remains'}
 [ordered]@{passed=$true;adapterCalls=$count;jobStatus=$job.status;temporaryFiles='cleaned'}|ConvertTo-Json
}finally{if(Test-Path $temp){Remove-Item $temp -Recurse -Force}}

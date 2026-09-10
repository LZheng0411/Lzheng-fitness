$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$null=[Windows.System.Launcher,Windows.System,ContentType=WindowsRuntime]
$null=[Windows.System.LaunchQuerySupportStatus,Windows.System,ContentType=WindowsRuntime]
$operation=[Windows.System.Launcher]::QueryUriSupportAsync([uri]'lzheng-fitness-agent://run',[Windows.System.LaunchQuerySupportType]::Uri)
$method=([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.IsGenericMethod -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' } | Select-Object -First 1).MakeGenericMethod([Windows.System.LaunchQuerySupportStatus])
$task=$method.Invoke($null,@($operation))
if(-not $task.Wait(10000)){throw 'Windows URI support query timed out'}
[string]$task.Result

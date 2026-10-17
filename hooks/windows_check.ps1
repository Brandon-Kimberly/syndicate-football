# Scheduled wrapper for scripts.run_windows (2026-09-04). The task used to run the
# script bare in a console that closed instantly, which made the daily check useless.
# This wrapper (a) appends the full report to data\windows_check.log so every run is
# reviewable, and (b) pops a persistent message box ONLY when something needs a human NOW:
# a MISSED window, an OPEN window inside ~a day of its deadline, or freshness that is stale
# for a reason a human must act on. Quiet days stay quiet. FLAG and RELEASE lines stay in the
# report and the log but do not pop: they re-fire every day while their condition holds, and
# a reminder that pops daily gets ignored (2026-10-17). The box shows only the lines that
# triggered it, not the whole report; the full text is in data\windows_check.log.
#
# Task Scheduler action (set once):
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden
#     -File "<repo>\hooks\windows_check.ps1"
# Run with -Quiet to log without ever showing the popup (used for testing).
# Run with -TestOutput "<text>" to drive the decision logic against sample text: no
# run_windows call, no log write, no popup -- just the verdict on stdout.
param([switch]$Quiet, [string]$TestOutput)

$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$logPath = Join-Path $repo "data\windows_check.log"

if ($TestOutput) {
    $output = $TestOutput
} else {
    if ((Test-Path $logPath) -and ((Get-Item $logPath).Length -gt 1MB)) {
        Move-Item -Force $logPath ($logPath + ".old")
    }
    $output = & py -3.10 -m scripts.run_windows 2>&1 | Out-String
    $stamp = (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ")
    Add-Content -Path $logPath -Encoding utf8 -Value ("=== $stamp ===`r`n" + $output)
}

$attention = $false
$why = @()
# Case-sensitive on purpose: a window status is upper case, and -match is case-insensitive, so
# the word 'missed' inside a sync warning popped the box (2026-10-17). FLAG and RELEASE do not
# pop (see the header); they are in the report and the log.
if ($output -cmatch '\bMISSED\s+run\d') { $attention = $true; $why += 'a window was MISSED' }

# Freshness: alarm only on staleness a human must act on. "simulation export predates
# the sync" is the local-only state that EVERY ad-hoc sync leaves behind -- gameday
# syncs without re-running the engine, by design -- and the orchestrator itself ignores
# that same criterion at entry (freshness.assess check_export=False) because its own
# next step re-simulates. Alarming on it would fire after every gameday run and train
# the popup to be ignored, which is the one failure this whole channel exists to avoid
# (2026-09-10: it did exactly that, on a diagnostic sync).
if ($output -match '(?s)freshness: STALE -- (.*?)(?:; degraded:|\r?\n)') {
    $real = ($Matches[1] -split ';\s*') | Where-Object {
        $_.Trim() -ne '' -and
        $_ -notmatch 'simulation export for week \d+ (predates the sync|is missing)'
    }
    if ($real.Count -gt 0) { $attention = $true; $why += ('stale: ' + ($real -join '; ')) }
}

foreach ($m in [regex]::Matches($output, '\bOPEN\s+run\d.*\((\d+(\.\d+)?) h remaining\)')) {
    if ([double]$m.Groups[1].Value -le 26.0) {
        $attention = $true; $why += 'a window closes within 26h'
    }
}

$verdict = if ($attention) { 'YES -- ' + (($why | Select-Object -Unique) -join '; ') } else { 'NO' }

if ($TestOutput) {
    Write-Output "attention: $verdict"
    return
}

Add-Content -Path $logPath -Encoding utf8 -Value "attention: $verdict`r`n"

if ($attention -and -not $Quiet) {
    Add-Type -AssemblyName System.Windows.Forms
    # Only what needs a human: the status, the window lines that triggered, and where the full
    # report is. The whole report (every baseline warning) made the box unreadable (2026-10-17).
    $fresh = if ($output -match 'freshness: (\w+)') { $Matches[1] } else { 'unknown' }
    $trig = @($output -split "`r?`n" | Where-Object { $_ -cmatch '\bMISSED\s+run\d|\bOPEN\s+run\d|^\s*>>' })
    $body = (@("Canonical run windows -- freshness: $fresh") + $trig + @("", "Full report: data\windows_check.log")) -join "`r`n"
    [void][System.Windows.Forms.MessageBox]::Show(
        $body,
        "Fantasy canonical windows -- attention needed",
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information)
}

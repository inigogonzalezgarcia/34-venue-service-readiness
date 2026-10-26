<#
.SYNOPSIS
    Read-only reachability check of the venue's devices, written as the devices.csv that venueready reads.

.DESCRIPTION
    Reads an inventory CSV (one row per device: Device, Outlet, Type, Model, IP, Port, Vendor, Role, Version, Target version, Next update)
    and probes each device from a machine on the venue network:
      - ICMP ping (Test-Connection), and when a Port is given, a TCP connection to that port (the POS service, the printer's 9100,
        the card terminal's payment port, the PMS interface's listener);
      - online when it answers, offline when it does not.
    It keeps the "Last seen" of every device between runs in -OutputFile: an online device gets the current time, an offline one keeps
    the last time it answered, so venueready can tell "down for 5 minutes" from "down since Wednesday".

    Columns the probe cannot know (cash level and fill of the cash machines, the PMS interface queue, error states shown only on the
    device) are copied from the inventory if present: fill them from the vendor consoles before the review.

    It only reads: no credentials, no changes to any device. Run it with PowerShell 7 for parallel probes (-ThrottleLimit).

.EXAMPLE
    .\scripts\Test-VenueDevices.ps1 -Inventory .\data\inventory.csv -OutputFile .\data\devices.csv
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory)] [string] $Inventory,
    [string] $OutputFile = '.\data\devices.csv',
    [int] $TimeoutSeconds = 2,
    [int] $ThrottleLimit = 16
)

$ErrorActionPreference = 'Stop'
$now = Get-Date -Format 'yyyy-MM-dd HH:mm'
$rows = Import-Csv -Path $Inventory
if (-not $rows) { throw "No rows in $Inventory" }

# last seen from the previous run
$previous = @{}
if (Test-Path $OutputFile) {
    foreach ($p in Import-Csv -Path $OutputFile) { if ($p.Device) { $previous[$p.Device] = $p.'Last seen' } }
}

function Test-Device([object] $row, [int] $timeout) {
    if (-not $row.IP) { return $null }
    $up = $false
    try {
        if ($PSVersionTable.PSVersion.Major -ge 7) {
            $up = Test-Connection -TargetName $row.IP -Count 1 -TimeoutSeconds $timeout -Quiet
        } else {
            $up = Test-Connection -ComputerName $row.IP -Count 1 -Quiet
        }
    } catch { $up = $false }
    if ($row.Port) {
        $client = [System.Net.Sockets.TcpClient]::new()
        try {
            $task = $client.ConnectAsync($row.IP, [int] $row.Port)
            $up = $task.Wait([TimeSpan]::FromSeconds($timeout)) -and $client.Connected
        } catch { $up = $false } finally { $client.Dispose() }
    }
    return $up
}

if ($PSVersionTable.PSVersion.Major -ge 7) {
    $fn = ${function:Test-Device}.ToString()
    $results = $rows | ForEach-Object -ThrottleLimit $ThrottleLimit -Parallel {
        ${function:Test-Device} = $using:fn
        [pscustomobject] @{ Device = $_.Device; Up = (Test-Device $_ $using:TimeoutSeconds) }
    }
} else {
    $results = foreach ($r in $rows) { [pscustomobject] @{ Device = $r.Device; Up = (Test-Device $r $TimeoutSeconds) } }
}
$up = @{}
foreach ($r in $results) { $up[$r.Device] = $r.Up }

$out = foreach ($r in $rows) {
    $state = $up[$r.Device]
    $status = if ($null -eq $state) { $r.Status } elseif ($state) { if ($r.Status -in 'degraded', 'error') { $r.Status } else { 'online' } } else { 'offline' }
    $seen = if ($state) { $now } else { $previous[$r.Device] }
    [pscustomobject] @{
        'Device'         = $r.Device
        'Outlet'         = $r.Outlet
        'Type'           = $r.Type
        'Model'          = $r.Model
        'Status'         = $status
        'Last seen'      = $seen
        'Version'        = $r.Version
        'Target version' = $r.'Target version'
        'Next update'    = $r.'Next update'
        'Vendor'         = $r.Vendor
        'Role'           = $r.Role
        'Cash level'     = $r.'Cash level'
        'Fill %'         = $r.'Fill %'
        'Queue'          = $r.Queue
    }
}

New-Item -ItemType Directory -Force -Path (Split-Path -Parent $OutputFile) | Out-Null
$out | Export-Csv -Path $OutputFile -NoTypeInformation -Encoding utf8
$down = @($out | Where-Object Status -ne 'online').Count
Write-Host "$($out.Count) devices checked at $now, $down not online -> $OutputFile"

# =============================================================
#  NETTOYAGE AUTOMATIQUE DU CACHE MICROSOFT EDGE
#  A deployer sur chaque caisse Windows
#  Planifie : au demarrage + chaque nuit a 05h00
# =============================================================

param(
    [string]$OdooUrl = "",          # Ex: "https://erp.sangel.com/pos/ui"
    [switch]$ReouvreEdge = $false   # Relancer Edge apres nettoyage
)

$LogFile = "$PSScriptRoot\cache_cleanup.log"

function Write-Log($Message) {
    $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$ts] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding UTF8
}

# --- 1. Fermer Edge proprement ---
Write-Log "Debut du nettoyage du cache Edge..."

$processes = Get-Process -Name "msedge" -ErrorAction SilentlyContinue
if ($processes) {
    Write-Log "Fermeture de Microsoft Edge ($($processes.Count) processus)..."
    Stop-Process -Name "msedge" -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 3
} else {
    Write-Log "Edge n'etait pas ouvert."
}

# --- 2. Chemins du cache a supprimer ---
$userProfile = $env:LOCALAPPDATA
$edgeBase    = "$userProfile\Microsoft\Edge\User Data"

$cachePaths = @(
    "$edgeBase\Default\Cache",
    "$edgeBase\Default\Code Cache",
    "$edgeBase\Default\GPUCache",
    "$edgeBase\Default\Service Worker\CacheStorage",
    "$edgeBase\Default\Service Worker\ScriptCache",
    "$edgeBase\Default\JumpListIcons",
    "$edgeBase\ShaderCache",
    "$edgeBase\GrShaderCache",
    "$edgeBase\PnaclTranslationCache"
)

# --- 3. Suppression ---
$totalSize = 0

foreach ($path in $cachePaths) {
    if (Test-Path $path) {
        try {
            $size = (Get-ChildItem $path -Recurse -ErrorAction SilentlyContinue |
                     Measure-Object -Property Length -Sum).Sum
            $totalSize += $size
            Remove-Item -Path $path -Recurse -Force -ErrorAction SilentlyContinue
            Write-Log "OK  Supprime : $path ($([math]::Round($size/1MB, 2)) Mo)"
        } catch {
            Write-Log "ERR Echec    : $path - $_"
        }
    }
}

$totalMo = [math]::Round($totalSize / 1MB, 2)
Write-Log "Nettoyage termine. Espace libere : $totalMo Mo"

# --- 4. Rotation du fichier log (garde 30 jours) ---
if (Test-Path $LogFile) {
    $lines = Get-Content $LogFile -Encoding UTF8
    $cutoff = (Get-Date).AddDays(-30).ToString("yyyy-MM-dd")
    $kept = $lines | Where-Object { $_ -match "^\[(\d{4}-\d{2}-\d{2})" -and $Matches[1] -ge $cutoff }
    if ($kept) { $kept | Set-Content $LogFile -Encoding UTF8 }
}

# --- 5. Rouvrir Edge (optionnel) ---
if ($ReouvreEdge) {
    $edgePath = "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
    if (-not (Test-Path $edgePath)) {
        $edgePath = "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
    }
    if (Test-Path $edgePath) {
        $args = @("--start-maximized")
        if ($OdooUrl) { $args += $OdooUrl }
        Start-Process $edgePath -ArgumentList $args
        Write-Log "Edge relance$( if ($OdooUrl) { ' sur ' + $OdooUrl } else { '' } )."
    }
}

Write-Log "--- Fin ---"

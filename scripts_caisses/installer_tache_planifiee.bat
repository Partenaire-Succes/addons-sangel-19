@echo off
:: =============================================================
::  INSTALLATION DE LA TACHE PLANIFIEE - NETTOYAGE CACHE EDGE
::  Lancer ce fichier UNE SEULE FOIS en tant qu'Administrateur
:: =============================================================

:: --- Configuration ---
set SCRIPT_DIR=%~dp0
set SCRIPT_PS1=%SCRIPT_DIR%clean_edge_cache.ps1
set TASK_NAME=NettoyageCacheEdgeCaisse

:: Verifier les droits admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo ERREUR: Lancez ce fichier en tant qu'Administrateur.
    echo Clic droit sur le fichier ^> "Executer en tant qu'administrateur"
    pause
    exit /b 1
)

echo ========================================
echo  Installation tache planifiee Windows
echo  Script : %SCRIPT_PS1%
echo ========================================
echo.

:: Supprimer l'ancienne tache si elle existe
schtasks /delete /tn "%TASK_NAME%" /f >nul 2>&1

:: --- Tache 1 : Au demarrage de Windows (apres connexion) ---
schtasks /create ^
  /tn "%TASK_NAME%_Demarrage" ^
  /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%SCRIPT_PS1%\"" ^
  /sc ONLOGON ^
  /delay 0001:00 ^
  /rl HIGHEST ^
  /f

if %errorlevel% equ 0 (
    echo [OK] Tache au demarrage creee.
) else (
    echo [ERR] Echec creation tache demarrage.
)

:: --- Tache 2 : Chaque nuit a 05h00 ---
schtasks /create ^
  /tn "%TASK_NAME%_Nuit" ^
  /tr "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File \"%SCRIPT_PS1%\"" ^
  /sc DAILY ^
  /st 05:00 ^
  /rl HIGHEST ^
  /f

if %errorlevel% equ 0 (
    echo [OK] Tache nocturne (05h00) creee.
) else (
    echo [ERR] Echec creation tache nocturne.
)

echo.
echo ========================================
echo  Taches installees avec succes.
echo  Pour verifier : Planificateur de taches
echo    ^> Bibliotheque ^> %TASK_NAME%_*
echo ========================================
echo.

:: Test immediat (optionnel)
set /p TEST="Lancer le nettoyage maintenant pour tester ? (O/N) : "
if /i "%TEST%"=="O" (
    powershell.exe -ExecutionPolicy Bypass -File "%SCRIPT_PS1%"
    echo.
    echo Log : %SCRIPT_DIR%cache_cleanup.log
)

pause

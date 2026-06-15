# =============================================================================
# tasks.ps1 - PowerShell task runner for lenreg-ticket-bot
# =============================================================================
# Usage: .\tasks.ps1 <command>
# Commands: install, lint, format, test, check, run, clean, lock, verify-pyproject
#
# Design rationale:
#   - Make is unavailable on Windows; this script provides the same interface.
#   - All tool paths are explicitly resolved (no PATH dependency).
#   - Poetry is invoked via `python -m poetry` (avoids PATH/encoding issues).
# =============================================================================

param(
  [Parameter(Mandatory = $true, Position = 0)]
  [ValidateSet("install", "lint", "format", "test", "check", "run", "clean", "lock", "verify-pyproject")]
  [string]$Command
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot

# -----------------------------------------------------------------------------
# Resolve tool paths
# -----------------------------------------------------------------------------
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { $Python = "python" }

$Npx = (Get-Command npx -ErrorAction SilentlyContinue).Source
if (-not $Npx) { $Npx = "npx" }

function Invoke-Poetry {
  param([string[]]$PoetryArgs)
  & $Python -m poetry @PoetryArgs
  if ($LASTEXITCODE -ne 0) { throw "Poetry command failed: poetry $PoetryArgs" }
}

function Invoke-Lint {
  Write-Host "=== Ruff check ===" -ForegroundColor Cyan
  & $Python -m ruff check src
  if ($LASTEXITCODE -ne 0) { throw "Ruff check failed" }

  Write-Host "=== Mypy ===" -ForegroundColor Cyan
  & $Python -m mypy src
  if ($LASTEXITCODE -ne 0) { throw "Mypy failed" }

  Write-Host "=== Markdownlint ===" -ForegroundColor Cyan
  & $Npx markdownlint "specs/**/*.md" ".roo/**/*.md" "*.md"
  if ($LASTEXITCODE -ne 0) { throw "Markdownlint failed" }

  Write-Host "Lint: all checks passed." -ForegroundColor Green
}

function Invoke-Format {
  Write-Host "=== Ruff format ===" -ForegroundColor Cyan
  & $Python -m ruff format src
  if ($LASTEXITCODE -ne 0) { throw "Ruff format failed" }

  Write-Host "=== Prettier ===" -ForegroundColor Cyan
  & $Npx prettier --write "specs/**/*.md" ".roo/**/*.md" "*.md"
  if ($LASTEXITCODE -ne 0) { throw "Prettier failed" }

  Write-Host "Format: done." -ForegroundColor Green
}

function Invoke-Test {
  Write-Host "=== Pytest ===" -ForegroundColor Cyan
  & $Python -m pytest tests/ -v
  if ($LASTEXITCODE -ne 0) { throw "Pytest failed" }
  Write-Host "Tests: all passed." -ForegroundColor Green
}

function Invoke-Run {
  Write-Host "=== Starting bot ===" -ForegroundColor Cyan
  & $Python -m src.main
}

function Invoke-Clean {
  Write-Host "=== Clean ===" -ForegroundColor Cyan
  Remove-Item -Recurse -Force -ErrorAction SilentlyContinue @(
    "$ProjectRoot/__pycache__",
    "$ProjectRoot/.pytest_cache",
    "$ProjectRoot/.mypy_cache",
    "$ProjectRoot/.ruff_cache"
  )
  # Clean src/__pycache__ recursively
  Get-ChildItem -Path "$ProjectRoot/src" -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force
  Get-ChildItem -Path "$ProjectRoot/tests" -Directory -Recurse -Filter "__pycache__" | Remove-Item -Recurse -Force
  Write-Host "Clean: done." -ForegroundColor Green
}

function Invoke-Check {
  # Full CI cycle: lint + format check + test
  Write-Host "=== Ruff check ===" -ForegroundColor Cyan
  & $Python -m ruff check src
  if ($LASTEXITCODE -ne 0) { throw "Ruff check failed" }

  Write-Host "=== Mypy ===" -ForegroundColor Cyan
  & $Python -m mypy src
  if ($LASTEXITCODE -ne 0) { throw "Mypy failed" }

  Write-Host "=== Markdownlint ===" -ForegroundColor Cyan
  & $Npx markdownlint "specs/**/*.md" ".roo/**/*.md" "*.md"
  if ($LASTEXITCODE -ne 0) { throw "Markdownlint failed" }

  Write-Host "=== Ruff format (check) ===" -ForegroundColor Cyan
  & $Python -m ruff format --check src
  if ($LASTEXITCODE -ne 0) { throw "Ruff format --check failed" }

  Write-Host "=== Prettier (check) ===" -ForegroundColor Cyan
  & $Npx prettier --check "specs/**/*.md" ".roo/**/*.md" "*.md"
  if ($LASTEXITCODE -ne 0) { throw "Prettier --check failed" }

  Write-Host "=== Pytest ===" -ForegroundColor Cyan
  & $Python -m pytest tests/ -v
  if ($LASTEXITCODE -ne 0) { throw "Pytest failed" }

  Write-Host "Check: all passed." -ForegroundColor Green
}

function Invoke-Install {
  Write-Host "=== Poetry install ===" -ForegroundColor Cyan
  Invoke-Poetry install

  Write-Host "=== npm install ===" -ForegroundColor Cyan
  & $Npx npm install
  if ($LASTEXITCODE -ne 0) { throw "npm install failed" }

  Write-Host "=== pre-commit install ===" -ForegroundColor Cyan
  & $Python -m pre_commit install
  if ($LASTEXITCODE -ne 0) { throw "pre-commit install failed" }

  Write-Host "Install: done." -ForegroundColor Green
}

function Invoke-Lock {
  Write-Host "=== Poetry lock ===" -ForegroundColor Cyan
  Invoke-Poetry lock
  Write-Host "Lock: done." -ForegroundColor Green
}

function Invoke-VerifyPyproject {
  Write-Host "=== Poetry check ===" -ForegroundColor Cyan
  Invoke-Poetry check
  Write-Host "verify-pyproject: pyproject.toml is valid." -ForegroundColor Green
}

# -----------------------------------------------------------------------------
# Dispatch
# -----------------------------------------------------------------------------
switch ($Command) {
  "install" { Invoke-Install }
  "lint" { Invoke-Lint }
  "format" { Invoke-Format }
  "test" { Invoke-Test }
  "check" { Invoke-Check }
  "run" { Invoke-Run }
  "clean" { Invoke-Clean }
  "lock" { Invoke-Lock }
  "verify-pyproject" { Invoke-VerifyPyproject }
}

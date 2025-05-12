# start_all.ps1
# Launch each Python script in its own PowerShell window,
# always from the project root so `import utils` works

# Path to your project root
$ProjectRoot = "C:\Users\User\PycharmProjects\Fiat_assist"

# Path to your venv python within that root
$Python = Join-Path $ProjectRoot "venv\Scripts\python.exe"

# List of scripts to run, relative to project root
$scripts = @(
    "bots\discord_bot.py",
    "monitors\flyboty.py",
    "monitors\newsfeeder.py",
    "monitors\newsquawk_recorder.py",
    "publishers\publisher.py",
    "publishers\publisher_v2.py"
)

foreach ($rel in $scripts) {
    $full = Join-Path $ProjectRoot $rel

    Start-Process -FilePath "powershell.exe" `
        -WorkingDirectory $ProjectRoot `
        -ArgumentList @(
            "-NoExit",
            "-Command", "& `"$Python`" `"$full`""
        )
}

' WerkZoeker — Silent Windows Background Launcher
Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strPath = fso.GetParentFolderName(WScript.ScriptFullName)

' Run python in silent background mode (window style 0 = hidden, bWaitOnReturn = False)
WshShell.CurrentDirectory = strPath
WshShell.Run strPath & "\.venv\Scripts\python.exe main.py --listen", 0, False

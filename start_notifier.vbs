Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' Launch Pythonw completely hidden (0 = hide window)
If fso.FileExists(".venv\Scripts\pythonw.exe") Then
    WshShell.Run ".venv\Scripts\pythonw.exe image_notifier.py", 0, False
Else
    WshShell.Run "pythonw.exe image_notifier.py", 0, False
End If

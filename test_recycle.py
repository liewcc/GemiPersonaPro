import os, ctypes
from ctypes import wintypes

def send_to_recycle_bin(path):
    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [
            ("hwnd", wintypes.HWND),
            ("wFunc", wintypes.UINT),
            ("pFrom", wintypes.LPCWSTR),
            ("pTo", wintypes.LPCWSTR),
            ("fFlags", wintypes.WORD),
            ("fAnyOperationsAborted", wintypes.BOOL),
            ("hNameMappings", wintypes.LPVOID),
            ("lpszProgressTitle", wintypes.LPCWSTR)
        ]

    FO_DELETE = 3
    FOF_ALLOWUNDO = 0x40
    FOF_NOCONFIRMATION = 0x10
    
    path_with_double_null = os.path.abspath(path) + '\0'
    
    shfos = SHFILEOPSTRUCTW()
    shfos.hwnd = None
    shfos.wFunc = FO_DELETE
    shfos.pFrom = path_with_double_null
    shfos.pTo = None
    shfos.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION
    shfos.fAnyOperationsAborted = False
    shfos.hNameMappings = None
    shfos.lpszProgressTitle = None

    result = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(shfos))
    if result != 0:
        raise Exception(f"Failed to move {path} to recycle bin, error code {result}")

with open("test_del.txt", "w") as f:
    f.write("test")
    
send_to_recycle_bin("test_del.txt")
print("Deleted to recycle bin successfully")

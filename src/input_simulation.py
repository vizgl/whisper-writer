import subprocess
import os
import signal
import sys
import time
from pynput.keyboard import Controller as PynputController

from utils import ConfigManager

# ---------------------------------------------------------------------------
#  Windows focus tracking via Win32 API
# ---------------------------------------------------------------------------
if sys.platform == 'win32':
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.GetFocus.restype = wintypes.HWND
    _user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    _user32.SetForegroundWindow.restype = wintypes.BOOL
    _user32.SetFocus.argtypes = [wintypes.HWND]
    _user32.SetFocus.restype = wintypes.HWND
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.restype = wintypes.BOOL
    _user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND, ctypes.POINTER(wintypes.DWORD),
    ]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    _user32.AttachThreadInput.argtypes = [
        wintypes.DWORD, wintypes.DWORD, wintypes.BOOL,
    ]
    _user32.AttachThreadInput.restype = wintypes.BOOL
    _kernel32.GetCurrentThreadId.restype = wintypes.DWORD

    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    _user32.ClientToScreen.restype = wintypes.BOOL

    class GUITHREADINFO(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.DWORD),
            ("flags", wintypes.DWORD),
            ("hwndActive", wintypes.HWND),
            ("hwndFocus", wintypes.HWND),
            ("hwndCapture", wintypes.HWND),
            ("hwndMenuOwner", wintypes.HWND),
            ("hwndMoveSize", wintypes.HWND),
            ("hwndCaret", wintypes.HWND),
            ("rcCaret", wintypes.RECT),
        ]

    _user32.GetGUIThreadInfo.argtypes = [wintypes.DWORD, ctypes.POINTER(GUITHREADINFO)]
    _user32.GetGUIThreadInfo.restype = wintypes.BOOL

def run_command_or_exit_on_failure(command):
    """
    Run a shell command and exit if it fails.

    Args:
        command (list): The command to run as a list of strings.
    """
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running command: {e}")
        exit(1)

class InputSimulator:
    """
    A class to simulate keyboard input using various methods.
    """

    def __init__(self):
        """
        Initialize the InputSimulator with the specified configuration.
        """
        self.input_method = ConfigManager.get_config_value('post_processing', 'input_method')
        self.dotool_process = None
        self._target_hwnd = None
        self._target_focus_hwnd = None

        if self.input_method == 'pynput':
            self.keyboard = PynputController()
        elif self.input_method == 'dotool':
            self._initialize_dotool()

    def _initialize_dotool(self):
        """
        Initialize the dotool process for input simulation.
        """
        self.dotool_process = subprocess.Popen("dotool", stdin=subprocess.PIPE, text=True)
        assert self.dotool_process.stdin is not None

    def _terminate_dotool(self):
        """
        Terminate the dotool process if it's running.
        """
        if self.dotool_process:
            os.kill(self.dotool_process.pid, signal.SIGINT)
            self.dotool_process = None

    # ------------------------------------------------------------------
    #  Focus save / restore  (Windows only, no-op on other platforms)
    # ------------------------------------------------------------------

    def save_target_window(self):
        """Remember the foreground window and its focused control."""
        if sys.platform != 'win32':
            return
        try:
            hwnd = _user32.GetForegroundWindow()
            if not hwnd:
                return

            self._target_hwnd = hwnd
            self._target_focus_hwnd = None

            remote_tid = _user32.GetWindowThreadProcessId(hwnd, None)
            my_tid = _kernel32.GetCurrentThreadId()

            if remote_tid and my_tid != remote_tid:
                _user32.AttachThreadInput(my_tid, remote_tid, True)
                try:
                    self._target_focus_hwnd = _user32.GetFocus()
                finally:
                    _user32.AttachThreadInput(my_tid, remote_tid, False)
            else:
                self._target_focus_hwnd = _user32.GetFocus()

            ConfigManager.console_print(
                f"Saved target window: hwnd={self._target_hwnd}, "
                f"focus={self._target_focus_hwnd}"
            )
        except Exception as e:
            ConfigManager.console_print(f"Failed to save target window: {e}")

    def _restore_target_window(self):
        """Restore focus to the previously saved window and control."""
        if sys.platform != 'win32' or not self._target_hwnd:
            return
        try:
            if not _user32.IsWindow(self._target_hwnd):
                ConfigManager.console_print("Target window no longer exists")
                self._target_hwnd = None
                self._target_focus_hwnd = None
                return

            my_tid = _kernel32.GetCurrentThreadId()

            # Attach to the current foreground thread so
            # SetForegroundWindow is allowed to succeed.
            fg_hwnd = _user32.GetForegroundWindow()
            fg_tid = 0
            if fg_hwnd and fg_hwnd != self._target_hwnd:
                fg_tid = _user32.GetWindowThreadProcessId(fg_hwnd, None)
                if fg_tid and my_tid != fg_tid:
                    _user32.AttachThreadInput(my_tid, fg_tid, True)

            _user32.SetForegroundWindow(self._target_hwnd)

            if fg_tid and my_tid != fg_tid:
                _user32.AttachThreadInput(my_tid, fg_tid, False)

            # Restore the exact child control that had focus.
            if (self._target_focus_hwnd
                    and _user32.IsWindow(self._target_focus_hwnd)):
                target_tid = _user32.GetWindowThreadProcessId(
                    self._target_hwnd, None,
                )
                attached = False
                if target_tid and my_tid != target_tid:
                    attached = bool(
                        _user32.AttachThreadInput(my_tid, target_tid, True)
                    )
                try:
                    _user32.SetFocus(self._target_focus_hwnd)
                finally:
                    if attached:
                        _user32.AttachThreadInput(my_tid, target_tid, False)

            time.sleep(0.05)
            ConfigManager.console_print("Restored target window focus")
        except Exception as e:
            ConfigManager.console_print(f"Failed to restore target window: {e}")

    def get_target_position(self):
        """Return (x, y) screen coordinates below the focused input field, or None."""
        if sys.platform != 'win32' or not self._target_hwnd:
            return None
        try:
            tid = _user32.GetWindowThreadProcessId(self._target_hwnd, None)
            if not tid:
                return None

            gti = GUITHREADINFO()
            gti.cbSize = ctypes.sizeof(GUITHREADINFO)
            if _user32.GetGUIThreadInfo(tid, ctypes.byref(gti)) and gti.hwndCaret:
                pt = wintypes.POINT(gti.rcCaret.left, gti.rcCaret.bottom)
                _user32.ClientToScreen(gti.hwndCaret, ctypes.byref(pt))
                return (pt.x, pt.y)

            # Fallback: use the focused child control rect
            hwnd = self._target_focus_hwnd or self._target_hwnd
            if hwnd and _user32.IsWindow(hwnd):
                rc = wintypes.RECT()
                if _user32.GetWindowRect(hwnd, ctypes.byref(rc)):
                    return (rc.left + (rc.right - rc.left) // 2, rc.bottom)
        except Exception as e:
            ConfigManager.console_print(f"Failed to get target position: {e}")
        return None

    # ------------------------------------------------------------------

    def typewrite(self, text):
        """
        Simulate typing the given text with the specified interval between keystrokes.

        Args:
            text (str): The text to type.
        """
        self._restore_target_window()
        interval = ConfigManager.get_config_value('post_processing', 'writing_key_press_delay')
        if self.input_method == 'pynput':
            self._typewrite_pynput(text, interval)
        elif self.input_method == 'ydotool':
            self._typewrite_ydotool(text, interval)
        elif self.input_method == 'dotool':
            self._typewrite_dotool(text, interval)

    def _typewrite_pynput(self, text, interval):
        """
        Simulate typing using pynput via clipboard paste for instant input.
        """
        import pyperclip
        from pynput.keyboard import Key

        old_clipboard = pyperclip.paste()
        pyperclip.copy(text)
        self.keyboard.press(Key.ctrl)
        self.keyboard.press('v')
        self.keyboard.release('v')
        self.keyboard.release(Key.ctrl)
        time.sleep(0.05)
        pyperclip.copy(old_clipboard)

    def _typewrite_ydotool(self, text, interval):
        """
        Simulate typing using ydotool.

        Args:
            text (str): The text to type.
            interval (float): The interval between keystrokes in seconds.
        """
        cmd = "ydotool"
        run_command_or_exit_on_failure([
            cmd,
            "type",
            "--key-delay",
            str(interval * 1000),
            "--",
            text,
        ])

    def _typewrite_dotool(self, text, interval):
        """
        Simulate typing using dotool.

        Args:
            text (str): The text to type.
            interval (float): The interval between keystrokes in seconds.
        """
        assert self.dotool_process and self.dotool_process.stdin
        self.dotool_process.stdin.write(f"typedelay {interval * 1000}\n")
        self.dotool_process.stdin.write(f"type {text}\n")
        self.dotool_process.stdin.flush()

    def cleanup(self):
        """
        Perform cleanup operations, such as terminating the dotool process.
        """
        if self.input_method == 'dotool':
            self._terminate_dotool()

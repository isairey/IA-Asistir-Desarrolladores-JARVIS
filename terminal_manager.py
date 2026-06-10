"""Terminal manager module for handling terminal emulation using xterm.js."""

# pylama:ignore=E501,C901
import os
import platform
import re
import select
import signal
import struct
import threading
import time
from threading import Thread

# Import platform-specific modules
if platform.system() != "Windows":
    import fcntl
    import pty
    import termios
else:
    from winpty import PTY


class TerminalManager:

    def __init__(self, socket):
        self.socket = socket
        self.fd = None
        self.pid = None
        self.process = None
        self.running = False
        self.is_windows = platform.system() == "Windows"
        self.pty = None
        self.read_thread = None
        self.workspace_dir = None

    def start(self, cols, rows, workspace_dir=None):
        self.workspace_dir = workspace_dir or os.getcwd()
        if self.is_windows:
            self._start_windows_terminal(cols, rows)
        else:
            self._start_unix_terminal(cols, rows)

    def _start_windows_terminal(self, cols, rows):
        try:
            # Create PTY with dimensions
            self.pty = PTY(rows, cols)

            # Start cmd.exe first
            self.pty.spawn("cmd.exe")

            # Wait a bit for cmd to initialize
            time.sleep(0.1)

            # Get the workspace path from the environment or current directory
            workspace_path = self.workspace_dir
            if workspace_path.startswith("/home"):
                # Convert WSL path to Windows path if needed
                workspace_path = workspace_path.replace("/home", "C:\\Users")
            workspace_path = workspace_path.replace("/", "\\")

            print(f"Changing to directory: {workspace_path}")  # Debug print

            # Send commands one by one
            self.pty.write(f'cd /d "{workspace_path}\\workspaces"\r\n')
            time.sleep(0.1)
            self.pty.write("cls\r\n")
            time.sleep(0.1)
            self.pty.write(f"mode CON: COLS={cols} LINES={rows}\r\n")

            # Start reading thread
            self.running = True
            self.read_thread = Thread(target=self._read_windows_output)
            self.read_thread.daemon = True
            self.read_thread.start()

        except Exception as e:
            print(f"Failed to start Windows terminal: {e}")
            self.cleanup()

    def _read_windows_output(self):
        """Thread that reads from the terminal and emits output"""
        while self.running and self.pty:
            try:
                # Read available data
                data = self.pty.read()
                if data:
                    # Clean and emit immediately
                    self.socket.emit("terminal_output", data)
                time.sleep(0.001)  # Tiny sleep to prevent CPU hogging
            except Exception as e:
                if "EOF" not in str(e):  # Don't print EOF errors
                    print(f"Error reading from Windows terminal: {e}")
                time.sleep(0.1)  # Sleep on error to prevent rapid retries
                if "EOF" in str(e):
                    break
                continue

        self.cleanup()

    def _clean_terminal_output(self, output):
        """Clean up terminal output by handling control sequences"""
        if self.is_windows:
            # Remove the chcp command output
            if "Active code page:" in output:
                output = output.split("\n", 1)[1] if "\n" in output else ""

            # Normalize line endings
            output = output.replace("\r\n", "\n")
            output = output.replace("\r", "\n")

            # Remove null bytes
            output = output.replace("\x00", "")

            # Remove duplicate empty lines
            while "\n\n\n" in output:
                output = output.replace("\n\n\n", "\n\n")

            return output.strip()
        return output

    def _strip_ansi(self, text):
        """Remove ANSI escape sequences"""
        ansi_escape = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
        return ansi_escape.sub("", text)

    def write(self, data):
        if self.is_windows:
            if self.pty:
                try:
                    # Handle cd command for Windows
                    if data.startswith('cd "') and data.endswith('"\n'):
                        path = data[4:-2]  # Extract path from cd "path"\n
                        # Convert Unix-style path to Windows path if needed
                        if path.startswith("/home"):
                            path = path.replace("/home", "C:\\Users")
                        path = path.replace("/", "\\")
                        # Use /d switch for cross-drive directory changes
                        windows_cmd = f'cd /d "{path}"\r\n'
                        with threading.Lock():
                            self.pty.write(windows_cmd)
                    else:
                        # Ensure input is processed as a single operation
                        with threading.Lock():
                            self.pty.write(data)
                except Exception as e:
                    print(f"Failed to write to Windows terminal: {e}")
        else:
            if self.fd is not None:
                try:
                    # For Unix, send the command as is
                    os.write(self.fd, data.encode())
                except Exception as e:
                    print(f"Failed to write to terminal: {e}")

    def resize_terminal(self, cols, rows):
        if self.is_windows:
            if self.pty:
                try:
                    # Use the mode command to resize the console
                    resize_command = f"mode CON: COLS={cols} LINES={rows}\r\n"
                    self.pty.write(resize_command)
                except Exception as e:
                    print(f"Failed to resize Windows terminal: {e}")
        else:
            if self.fd is not None:
                try:
                    size = struct.pack("HHHH", rows, cols, 0, 0)
                    fcntl.ioctl(self.fd, termios.TIOCSWINSZ, size)
                except Exception as e:
                    print(f"Failed to resize terminal: {e}")

    def cleanup(self):
        self.running = False

        if self.is_windows:
            if self.pty:
                try:
                    self.pty.close()
                except BaseException:
                    pass
                self.pty = None
        else:
            if self.pid:
                try:
                    os.kill(self.pid, signal.SIGTERM)
                except BaseException:
                    pass

            if self.fd is not None:
                try:
                    os.close(self.fd)
                except BaseException:
                    pass

            self.fd = None
            self.pid = None

    def _start_unix_terminal(self, cols, rows):
        # Choose shell based on environment
        shell = os.environ.get("SHELL", "/bin/bash")

        # Create PTY and fork process
        self.pid, self.fd = pty.fork()

        if self.pid == 0:  # Child process
            try:
                # Set up environment
                os.environ["TERM"] = "xterm-256color"
                os.environ["COLORTERM"] = "truecolor"

                # Start shell
                os.execvp(shell, [shell])
            except Exception as e:
                print(f"Failed to execute shell: {e}")
                os._exit(1)
        else:  # Parent process
            try:
                # Set terminal size
                self.resize_terminal(cols, rows)

                # Wait a bit for shell to initialize
                time.sleep(0.1)

                # Get the workspace path
                workspace_path = self.workspace_dir
                # Debug print
                print(f"Changing to directory: {workspace_path}")

                # Send commands one by one
                os.write(self.fd,
                         f'cd "{workspace_path}/workspaces"\n'.encode())
                time.sleep(0.1)
                os.write(self.fd, "clear\n".encode())

                # Start reading thread
                self.running = True
                self.thread = Thread(target=self._read_unix_output)
                self.thread.daemon = True
                self.thread.start()
            except Exception as e:
                print(f"Failed to initialize terminal: {e}")
                self.cleanup()

    def _read_unix_output(self):
        max_read_bytes = 1024 * 20

        while self.running and self.fd is not None:
            try:
                r, _, _ = select.select([self.fd], [], [], 0.1)
                if r:
                    output = os.read(self.fd, max_read_bytes)
                    if output:
                        # Emit the output to the client
                        self.socket.emit("terminal_output",
                                         output.decode(errors="replace"))
                    else:
                        # EOF reached
                        break
            except Exception as e:
                print(f"Error reading from Unix terminal: {e}")
                break

        self.cleanup()

    # ... rest of the Unix terminal methods stay the same ...

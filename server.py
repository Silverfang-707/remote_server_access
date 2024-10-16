# server.py
import socket
import ssl
import threading
import pyautogui
import keyboard
import win32gui
import win32con
import win32api
import os
from PIL import ImageGrab
import io
import json
from pathlib import Path
import tkinter as tk
from tkinter import messagebox

class RestrictedPaths:
    def __init__(self):
        self.restricted_paths = set([
            os.path.expanduser('~'),  # User directory
            os.path.expandvars('%WINDIR%'),  # Windows directory
            os.path.expandvars('%PROGRAMFILES%'),  # Program Files
            os.path.expandvars('%PROGRAMFILES(X86)%')  # Program Files (x86)
        ])
    
    def is_restricted(self, path):
        path = Path(path).resolve()
        return any(str(path).startswith(str(Path(rp).resolve())) for rp in self.restricted_paths)
    
    def add_restricted_path(self, path):
        self.restricted_paths.add(str(Path(path).resolve()))
    
    def remove_restricted_path(self, path):
        self.restricted_paths.discard(str(Path(path).resolve()))

class SecureServer:
    def __init__(self, host='0.0.0.0', port=4443):
        self.host = host
        self.port = port
        self.screen_width, self.screen_height = pyautogui.size()
        self.restricted_paths = RestrictedPaths()
        
        # Disable PyAutoGUI fail-safe
        pyautogui.FAILSAFE = False
        
        # SSL setup
        self.setup_ssl()
        
        # Create socket
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(1)
        
        # Control flags
        self.running = False
        self.allow_input = True
        
        # GUI setup
        self.setup_gui()
    
    def setup_ssl(self):
        self.context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
        self.context.load_cert_chain(certfile='server.crt', keyfile='server.key')
        self.context.verify_mode = ssl.CERT_REQUIRED
        self.context.load_verify_locations(cafile='rootCA.crt')
    
    def setup_gui(self):
        self.root = tk.Tk()
        self.root.title("Remote Control Server")
        
        # Status Frame
        status_frame = tk.LabelFrame(self.root, text="Server Status")
        status_frame.pack(padx=5, pady=5, fill=tk.X)
        
        self.status_label = tk.Label(status_frame, text="Stopped")
        self.status_label.pack(pady=5)
        
        # Control Frame
        control_frame = tk.LabelFrame(self.root, text="Controls")
        control_frame.pack(padx=5, pady=5, fill=tk.X)
        
        self.start_button = tk.Button(control_frame, text="Start Server", command=self.start_server)
        self.start_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        self.stop_button = tk.Button(control_frame, text="Stop Server", command=self.stop_server, state=tk.DISABLED)
        self.stop_button.pack(side=tk.LEFT, padx=5, pady=5)
        
        # Input Control Frame
        input_frame = tk.LabelFrame(self.root, text="Input Control")
        input_frame.pack(padx=5, pady=5, fill=tk.X)
        
        self.input_var = tk.BooleanVar(value=True)
        self.input_check = tk.Checkbutton(input_frame, text="Allow Remote Input", 
                                        variable=self.input_var, 
                                        command=self.toggle_input)
        self.input_check.pack(pady=5)
        
        # Restricted Paths Frame
        paths_frame = tk.LabelFrame(self.root, text="Restricted Paths")
        paths_frame.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        
        self.paths_list = tk.Listbox(paths_frame)
        self.paths_list.pack(padx=5, pady=5, fill=tk.BOTH, expand=True)
        
        paths_button_frame = tk.Frame(paths_frame)
        paths_button_frame.pack(fill=tk.X)
        
        tk.Button(paths_button_frame, text="Add Path", 
                 command=self.add_restricted_path).pack(side=tk.LEFT, padx=5, pady=5)
        tk.Button(paths_button_frame, text="Remove Path", 
                 command=self.remove_restricted_path).pack(side=tk.LEFT, padx=5, pady=5)
        
        self.update_paths_list()
    
    def update_paths_list(self):
        self.paths_list.delete(0, tk.END)
        for path in sorted(self.restricted_paths.restricted_paths):
            self.paths_list.insert(tk.END, path)
    
    def add_restricted_path(self):
        from tkinter import filedialog
        path = filedialog.askdirectory()
        if path:
            self.restricted_paths.add_restricted_path(path)
            self.update_paths_list()
    
    def remove_restricted_path(self):
        selection = self.paths_list.curselection()
        if selection:
            path = self.paths_list.get(selection[0])
            self.restricted_paths.remove_restricted_path(path)
            self.update_paths_list()
    
    def toggle_input(self):
        self.allow_input = self.input_var.get()
    
    def handle_mouse_event(self, event_data):
        if not self.allow_input:
            return
        
        event_type = event_data['type']
        x, y = event_data['x'], event_data['y']
        
        if event_type == 'move':
            win32api.SetCursorPos((x, y))
        elif event_type == 'click':
            button = event_data.get('button', 'left')
            state = event_data.get('state', 'down')
            
            if button == 'left':
                if state == 'down':
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTDOWN, x, y, 0, 0)
                else:
                    win32api.mouse_event(win32con.MOUSEEVENTF_LEFTUP, x, y, 0, 0)
            elif button == 'right':
                if state == 'down':
                    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTDOWN, x, y, 0, 0)
                else:
                    win32api.mouse_event(win32con.MOUSEEVENTF_RIGHTUP, x, y, 0, 0)
    
    def handle_keyboard_event(self, event_data):
        if not self.allow_input:
            return
        
        key = event_data['key']
        state = event_data['state']  # 'down' or 'up'
        
        if state == 'down':
            keyboard.press(key)
        else:
            keyboard.release(key)
    
    def handle_file_access(self, path):
        return not self.restricted_paths.is_restricted(path)
    
    def handle_client(self, conn, addr):
        try:
            self.status_label.config(text=f"Connected to {addr}")
            
            while True:
                # Receive message size first
                size_data = conn.recv(8)
                if not size_data:
                    break
                
                msg_size = int.from_bytes(size_data, byteorder='big')
                
                # Receive full message
                data = b''
                while len(data) < msg_size:
                    chunk = conn.recv(min(msg_size - len(data), 4096))
                    if not chunk:
                        break
                    data += chunk
                
                if not data:
                    break
                
                message = json.loads(data.decode())
                
                if message['type'] == 'mouse':
                    self.handle_mouse_event(message['data'])
                elif message['type'] == 'keyboard':
                    self.handle_keyboard_event(message['data'])
                elif message['type'] == 'screenshot':
                    # Take screenshot and send
                    screenshot = ImageGrab.grab()
                    img_bytes = io.BytesIO()
                    screenshot.save(img_bytes, format='PNG')
                    size = len(img_bytes.getvalue())
                    conn.send(size.to_bytes(8, byteorder='big'))
                    conn.sendall(img_bytes.getvalue())
                elif message['type'] == 'file_access':
                    # Check if file access is allowed
                    allowed = self.handle_file_access(message['data']['path'])
                    response = json.dumps({'allowed': allowed}).encode()
                    size = len(response)
                    conn.send(size.to_bytes(8, byteorder='big'))
                    conn.sendall(response)
                
        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            conn.close()
            self.status_label.config(text="Waiting for connection")
    
    def start_server(self):
        self.running = True
        self.status_label.config(text="Waiting for connection")
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        
        def server_loop():
            while self.running:
                try:
                    client_sock, addr = self.sock.accept()
                    ssl_conn = self.context.wrap_socket(client_sock, server_side=True)
                    client_thread = threading.Thread(target=self.handle_client, 
                                                  args=(ssl_conn, addr))
                    client_thread.start()
                except Exception as e:
                    if self.running:
                        print(f"Error accepting connection: {e}")
        
        self.server_thread = threading.Thread(target=server_loop)
        self.server_thread.start()
    
    def stop_server(self):
        self.running = False
        self.sock.close()
        self.status_label.config(text="Stopped")
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    server = SecureServer()
    server.run()
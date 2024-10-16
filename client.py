import socket
import ssl
import json
import threading
import tkinter as tk
from PIL import Image, ImageTk
import io
from datetime import datetime

class SecureClient:
    def __init__(self, host='localhost', port=4443):
        self.host = host
        self.port = port
        
        # SSL setup
        self.setup_ssl()
        
        # Screen properties
        self.remote_width = 1920  # Default, will be updated
        self.remote_height = 1080  # Default, will be updated
        
        # Initialize screenshot_interval before setup_gui
        self.screenshot_interval = 50  # ms
        
        # GUI setup
        self.setup_gui()
        
        self.conn = None
        self.running = False
        self.screenshot_thread = None
        
        # Mouse and keyboard tracking
        self.last_mouse_pos = (0, 0)
        self.pressed_keys = set()
        
        # Performance settings
        self.mouse_threshold = 5  # pixels
    
    def setup_ssl(self):
        self.context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        self.context.load_cert_chain(certfile='client.crt', keyfile='client.key')
        self.context.load_verify_locations(cafile='rootCA.crt')
        self.context.check_hostname = False
    
    def setup_gui(self):
        self.root = tk.Tk()
        self.root.title("Remote Control Client")
        
        # Main container
        main_container = tk.Frame(self.root)
        main_container.pack(fill=tk.BOTH, expand=True)
        
        # Left panel for controls
        left_panel = tk.Frame(main_container)
        left_panel.pack(side=tk.LEFT, fill=tk.Y, padx=5, pady=5)
        
        # Connection Frame
        conn_frame = tk.LabelFrame(left_panel, text="Connection")
        conn_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(conn_frame, text="Host:").pack(padx=5, pady=2)
        self.host_entry = tk.Entry(conn_frame)
        self.host_entry.insert(0, self.host)
        self.host_entry.pack(padx=5, pady=2, fill=tk.X)
        
        tk.Label(conn_frame, text="Port:").pack(padx=5, pady=2)
        self.port_entry = tk.Entry(conn_frame)
        self.port_entry.insert(0, str(self.port))
        self.port_entry.pack(padx=5, pady=2, fill=tk.X)
        
        self.connect_button = tk.Button(conn_frame, text="Connect", command=self.toggle_connection)
        self.connect_button.pack(padx=5, pady=5, fill=tk.X)
        
        # Status Frame
        status_frame = tk.LabelFrame(left_panel, text="Status")
        status_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.status_label = tk.Label(status_frame, text="Disconnected")
        self.status_label.pack(padx=5, pady=5)
        
        # Performance Frame
        perf_frame = tk.LabelFrame(left_panel, text="Performance")
        perf_frame.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(perf_frame, text="Refresh Rate (ms):").pack(padx=5, pady=2)
        self.refresh_scale = tk.Scale(perf_frame, from_=16, to=200, orient=tk.HORIZONTAL, command=self.update_refresh_rate)
        self.refresh_scale.set(self.screenshot_interval)
        self.refresh_scale.pack(padx=5, pady=2, fill=tk.X)
        
        # Quality Frame
        quality_frame = tk.LabelFrame(left_panel, text="Image Quality")
        quality_frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.quality_var = tk.IntVar(value=85)
        self.quality_scale = tk.Scale(quality_frame, from_=1, to=100, orient=tk.HORIZONTAL, variable=self.quality_var)
        self.quality_scale.pack(padx=5, pady=2, fill=tk.X)
        
        # Remote View Frame
        view_frame = tk.LabelFrame(main_container, text="Remote View")
        view_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.canvas = tk.Canvas(view_frame, bg='black')
        self.canvas.pack(fill=tk.BOTH, expand=True)
        
        # Bind events
        self.canvas.bind("<Motion>", self.on_mouse_motion)
        self.canvas.bind("<Button>", self.on_mouse_button)
        self.canvas.bind("<ButtonRelease>", self.on_mouse_release)
        self.canvas.bind("<MouseWheel>", self.on_mouse_wheel)
        self.canvas.bind("<Leave>", self.confine_mouse)
        
        self.root.bind("<Key>", self.on_key_press)
        self.root.bind("<KeyRelease>", self.on_key_release)
        
        # Status bar
        self.statusbar = tk.Label(self.root, text="", bd=1, relief=tk.SUNKEN, anchor=tk.W)
        self.statusbar.pack(side=tk.BOTTOM, fill=tk.X)
    
    def update_refresh_rate(self, value):
        self.screenshot_interval = int(value)
    
    def update_status(self, message):
        self.statusbar.config(text=f"{datetime.now().strftime('%H:%M:%S')}: {message}")
    
    def send_message(self, message):
        if not self.conn:
            return
        
        try:
            data = json.dumps(message).encode()
            size = len(data)
            self.conn.send(size.to_bytes(8, byteorder='big'))
            self.conn.sendall(data)
        except Exception as e:
            self.update_status(f"Error sending message: {e}")
            self.disconnect()
    
    def confine_mouse(self, event):
        x = self.root.winfo_pointerx() - self.canvas.winfo_rootx()
        y = self.root.winfo_pointery() - self.canvas.winfo_rooty()
        
        x = max(0, min(x, self.canvas.winfo_width() - 1))
        y = max(0, min(y, self.canvas.winfo_height() - 1))
        
        self.root.event_generate('<Motion>', warp=True, x=x, y=y)
    
    def on_mouse_motion(self, event):
        if not self.conn:
            return
        
        x = max(0, min(event.x, self.canvas.winfo_width() - 1))
        y = max(0, min(event.y, self.canvas.winfo_height() - 1))
        
        remote_x = x * (self.remote_width / self.canvas.winfo_width())
        remote_y = y * (self.remote_height / self.canvas.winfo_height())
        
        if abs(remote_x - self.last_mouse_pos[0]) > self.mouse_threshold or abs(remote_y - self.last_mouse_pos[1]) > self.mouse_threshold:
            self.send_message({
                'type': 'mouse',
                'data': {
                    'type': 'move',
                    'x': int(remote_x),
                    'y': int(remote_y)
                }
            })
            self.last_mouse_pos = (remote_x, remote_y)
    
    def on_mouse_button(self, event):
        if not self.conn:
            return
        
        button = 'left' if event.num == 1 else 'right' if event.num == 3 else None
        if button:
            x = event.x * (self.remote_width / self.canvas.winfo_width())
            y = event.y * (self.remote_height / self.canvas.winfo_height())
            
            self.send_message({
                'type': 'mouse',
                'data': {
                    'type': 'click',
                    'button': button,
                    'state': 'down',
                    'x': int(x),
                    'y': int(y)
                }
            })
    
    def on_mouse_release(self, event):
        if not self.conn:
            return
        
        button = 'left' if event.num == 1 else 'right' if event.num == 3 else None
        if button:
            x = event.x * (self.remote_width / self.canvas.winfo_width())
            y = event.y * (self.remote_height / self.canvas.winfo_height())
            
            self.send_message({
                'type': 'mouse',
                'data': {
                    'type': 'click',
                    'button': button,
                    'state': 'up',
                    'x': int(x),
                    'y': int(y)
                }
            })
    
    def on_mouse_wheel(self, event):
        if not self.conn:
            return
        
        self.send_message({
            'type': 'mouse',
            'data': {
                'type': 'wheel',
                'delta': event.delta
            }
        })
    
    def on_key_press(self, event):
        if not self.conn:
            return
        
        if event.keysym not in self.pressed_keys:
            self.pressed_keys.add(event.keysym)
            self.send_message({
                'type': 'keyboard',
                'data': {
                    'key': event.keysym,
                    'state': 'down'
                }
            })
    
    def on_key_release(self, event):
        if not self.conn:
            return
        
        if event.keysym in self.pressed_keys:
            self.pressed_keys.remove(event.keysym)
            self.send_message({
                'type': 'keyboard',
                'data': {
                    'key': event.keysym,
                    'state': 'up'
                }
            })
    
    def update_screenshot(self):
        while self.running:
            try:
                self.send_message({'type': 'screenshot'})
                
                size_data = self.conn.recv(8)
                if not size_data:
                    break
                
                size = int.from_bytes(size_data, byteorder='big')
                
                data = b''
                while len(data) < size:
                    chunk = self.conn.recv(min(size - len(data), 8192))
                    if not chunk:
                        break
                    data += chunk
                
                img = Image.open(io.BytesIO(data))
                self.remote_width, self.remote_height = img.size
                
                canvas_width = self.canvas.winfo_width()
                canvas_height = self.canvas.winfo_height()
                
                scale = min(canvas_width/self.remote_width, canvas_height/self.remote_height)
                
                new_width = int(self.remote_width * scale)
                new_height = int(self.remote_height * scale)
                
                if new_width > 0 and new_height > 0:
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    self.photo = ImageTk.PhotoImage(img)
                    self.canvas.delete("all")
                    self.canvas.create_image(canvas_width//2, canvas_height//2, image=self.photo, anchor=tk.CENTER)
                
                self.root.after(self.screenshot_interval, self.update_screenshot)
                break
                
            except Exception as e:
                self.update_status(f"Error updating screenshot: {e}")
                self.disconnect()
                break
    
    def connect(self):
        try:
            self.host = self.host_entry.get()
            self.port = int(self.port_entry.get())
            
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.conn = self.context.wrap_socket(sock, server_hostname=self.host)
            self.conn.connect((self.host, self.port))
            
            self.running = True
            self.connect_button.config(text="Disconnect")
            self.status_label.config(text="Connected")
            self.update_status("Connected to server")
            
            self.screenshot_thread = threading.Thread(target=self.update_screenshot)
            self.screenshot_thread.daemon = True
            self.screenshot_thread.start()
            
        except Exception as e:
            self.update_status(f"Connection error: {e}")
            self.disconnect()
    
    def disconnect(self):
        self.running = False
        if self.conn:
            self.conn.close()
            self.conn = None
        
        self.connect_button.config(text="Connect")
        self.status_label.config(text="Disconnected")
        self.update_status("Disconnected from server")
        self.canvas.delete("all")
    
    def toggle_connection(self):
        if self.conn:
            self.disconnect()
        else:
            self.connect()
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    client = SecureClient()
    client.run()
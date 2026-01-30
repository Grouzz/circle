import socket
from multiprocessing import shared_memory
import random
import struct
from queue import Empty
import os
import time
import signal


tab_size = 20
cell_size = 25
number_bytes = tab_size * tab_size

#network
HOST = "localhost"
PORT = 65501
shared_mem_name = "CircleGame"

#constants
energy_start = 50
energy_max = 100
h_lim = 40 #hunger limit (threshold to become active)
r_lim = 75       #reproduction limit
cost_move = 0.5
food_gain = 25

#local codes
empty = 0
grass = 1
passive_prey = 2
predator = 3
active_prey = 4

class EnvProcess:
    def __init__(self, grid_lock):
        self.lock = grid_lock
        self.running = True
        self.raining = False
        self.drought = False

    def signal_handler(self, sig, frame):
        self.drought = not self.drought
        print(f"<ENV> drought toggled: {self.drought}")

    def run(self, cmd_queue, display_queue):
        """main env process: it owns the shared memory and tries to send frames to display"""
        print(f"<ENV> starting. PID: {os.getpid()}")
        
        #drought
        signal.signal(signal.SIGUSR1, self.signal_handler) #trigger action to signal
        print("<ENV> SIGUSR1 handler registered for drought toggle")
        
        #shared mem
        try:
            self.shared = shared_memory.SharedMemory(name=shared_mem_name, create=True, size=number_bytes)
            self.is_owner = True
        except FileExistsError:
            #clean old mem
            try:
                old_shm = shared_memory.SharedMemory(name=shared_mem_name)
                old_shm.close() #close connection
                old_shm.unlink() #destroying it
            except:
                pass
            self.shared = shared_memory.SharedMemory(name=shared_mem_name, create=True, size=number_bytes)
            self.is_owner = True
        
        #data
        self.grid = self.shared.buf
        
        #initialisation
        for i in range(number_bytes):
            self.grid[i] = empty

        #socket for animal spawning
        self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) #reuse port if quick restart
        try:
            self.server_sock.bind((HOST, PORT))
            self.server_sock.listen(5) #backlog, ie max waiting room capacity
            self.server_sock.setblocking(False)
        except OSError:
            print(f"<ENV> port {PORT} busy, we can't actually start the game...")
            self.cleanup()
            return

        print(f"<ENV> listening on {HOST}:{PORT}")
        
        last_frame_time = time.time()
        frame_interval = 0.033  #30 FPS
        
        try:
            while self.running:
                self.growing_grass()

                #accepting new animals
                try:
                    conn, addr = self.server_sock.accept()
                    with self.lock:
                        start_pos = self.find_empty_spot()
                        if start_pos != -1:
                            conn.sendall(struct.pack("I", start_pos)) #int to 4 bytes binary data
                        else:
                            conn.close()
                    conn.close()

                except BlockingIOError:
                    pass

                #commands from display
                try:
                    while True:
                        cmd = cmd_queue.get_nowait()
                        if cmd == "quit":
                            self.running = False
                        elif cmd == "rain":
                            self.raining = not self.raining
                            print(f"<ENV> raining: {self.raining}")
                        elif cmd == "drought":
                            self.drought = not self.drought
                            print(f"<ENV> drought: {self.drought}")
                except Empty: #no more messages to treat
                    pass
                
                #sending frames
                current_time = time.time()
                if current_time - last_frame_time >= frame_interval: #to avoid flooding the queue
                    self.send_frame(display_queue)
                    last_frame_time = current_time
                
                time.sleep(0.01)  #sleep to prevent CPU from spinning
        except KeyboardInterrupt:
            pass
        finally:
            self.cleanup()

    def find_empty_spot(self):
        """find random empty spot for new animal"""
        attempts = 0
        while attempts < 100:
            position = random.randint(0, number_bytes - 1)
            if self.grid[position] == empty:
                return position
            attempts += 1
        return -1

    def growing_grass(self):
        """growing grass randomly unless drought is active"""
        if self.drought:
            return

        if self.raining:
            growth_chance = 0.25
        else:
            growth_chance = 0.10

        if random.random() < growth_chance:
            with self.lock:
                position = self.find_empty_spot()
                if position != -1:
                    self.grid[position] = grass

    def send_frame(self, display_queue):
        """send grid frame"""
        with self.lock:
            #copy of the grid state
            grid_copy = bytes(self.grid)
            
            #population count
            counts = {'grass': 0, 'passive_prey': 0, 'active_prey': 0, 'predator': 0}
            
            for i in range(number_bytes):
                val = self.grid[i]
                if val == grass:
                    counts['grass'] += 1
                elif val == passive_prey:
                    counts['passive_prey'] += 1
                elif val == active_prey:
                    counts['active_prey'] += 1
                elif val == predator:
                    counts['predator'] += 1

        frame = {'grid': grid_copy, 'counts': counts, 'raining': self.raining, 'drought': self.drought}
        
        #sending frame to display
        try:
            display_queue.put_nowait(frame)
        except:
            pass  #queue full, dropping this frame

    def cleanup(self):
        """cleaning up resources"""
        print("<ENV> cleaning up resources...")
        if hasattr(self, 'server_sock'):
            self.server_sock.close()
        if hasattr(self, 'shared'):
            self.shared.close()
            if self.is_owner:
                try:
                    self.shared.unlink()
                except:
                    pass
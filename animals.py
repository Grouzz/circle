import socket
import multiprocessing
from multiprocessing import shared_memory
import random
import struct
import time
import env

class Animal:
    """for predator and prey"""
    def __init__(self, species_type, grid_lock):
        self.species = species_type
        self.energy = env.energy_start
        self.pos_idx = -1
        self.lock = grid_lock
        self.running = True

    def run(self):
        """Main lifecycle of an animal"""
        #connectingto env
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.connect((env.HOST, env.PORT))
            data = sock.recv(4)
            if not data:
                return
            self.pos_idx = struct.unpack('I', data)[0]
            sock.close()
        except Exception as e:
            print(f"<ANIMAL> failed to connect: {e}")
            return

        #shared mem
        try:
            shm = shared_memory.SharedMemory(name=env.shared_mem_name)
            grid = shm.buf
        except FileNotFoundError:
            print("<ANIMAL> shared mem not found")
            return

        #placing self on grid
        with self.lock:
            if grid[self.pos_idx] == env.empty:
                grid[self.pos_idx] = self.species
            else:
                shm.close()
                return

        while self.running:
            time.sleep(random.uniform(0.5, 1.5)) #slowmotion for visibility
            self.energy -= env.cost_move #losing energy if movement
            
            #die if no energy
            if self.energy <= 0:
                self.die(grid)
                break

            #checking if self still alive
            current = grid[self.pos_idx]
            if self.species == env.predator:
                if current != env.predator:
                    break
            else:
                if current not in [env.passive_prey, env.active_prey]:
                    break

            #is it hungry
            is_active = self.energy < env.h_lim
            
            #updating prey visual state
            if self.species in [env.passive_prey, env.active_prey]:
                new_code = env.active_prey if is_active else env.passive_prey
                with self.lock:
                    if grid[self.pos_idx] in [env.passive_prey, env.active_prey]:
                        grid[self.pos_idx] = new_code
            
            self.move_and_eat(grid, is_active) #moving and try to eat

            #reproductionif enough energy
            if self.energy > env.r_lim:
                self.reproduce()
                self.energy -= 60

        shm.close()

    def die(self, grid):
        """removing from grid"""
        with self.lock:
            if grid[self.pos_idx] in [env.passive_prey, env.active_prey, env.predator]:
                grid[self.pos_idx] = env.empty

    def reproduce(self):
        """spawning a child animal"""
        child_type = env.passive_prey if self.species != env.predator else env.predator
        p = multiprocessing.Process(target=run_animal, args=(child_type, self.lock), daemon=True)
        p.start()

    def get_neighbors(self):
        """get list of neighboring cell indices"""
        row = self.pos_idx // env.tab_size
        col = self.pos_idx % env.tab_size
        neighbors = []
        legal_moves = [(-1, 0), (1, 0), (0, -1), (0, 1)]

        for dr, dc in legal_moves:
            nr, nc = row + dr, col + dc
            if 0 <= nr < env.tab_size and 0 <= nc < env.tab_size:
                neighbors.append(nr * env.tab_size + nc)
        return neighbors

    def move_and_eat(self, grid, is_active):
        """moving to neighbor and eat (if possible ofc)"""
        neighbors = self.get_neighbors()
        random.shuffle(neighbors)
        target = -1
        
        with self.lock:
            for n_idx in neighbors:
                content = grid[n_idx]
                if self.species in [env.passive_prey, env.active_prey]:
                    #prey eats grass when active
                    if is_active and content == env.grass:
                        self.energy = min(env.energy_max, self.energy +env.food_gain)
                        target = n_idx
                        break
                    elif content == env.empty:
                        target = n_idx
                
                elif self.species == env.predator:
                    #predator eats active prey when hungry
                    if is_active and content == env.active_prey:
                        self.energy = min(env.energy_max, self.energy+ env.food_gain)
                        target = n_idx
                        break
                    elif content == env.empty:
                        target = n_idx

            #executing the move that we've found
            if target != -1:
                if self.species in [env.passive_prey, env.active_prey]:
                    vis = env.active_prey if is_active else env.passive_prey
                else:
                    vis = self.species
                
                #move
                grid[self.pos_idx] = env.empty
                self.pos_idx = target
                grid[self.pos_idx] = vis


def run_animal(species, lock):
    """function to create and run an animal"""
    a = Animal(species, lock)
    a.run()
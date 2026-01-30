import pygame
import multiprocessing
from multiprocessing import shared_memory
import time
from queue import Empty
import sys
import env
import animals

#self.font = pygame.font.SysFont("Helvetica Neue", 16, bold=True)

bg_color = (181, 136, 99)      # Light wood (maple/beech)
grid_color = (240, 217, 181)   # Very light wood
text_color = (60, 40, 20)      # Dark brown

bg_color = (139, 69, 19)       # Dark walnut
grid_color = (222, 184, 135)   # Light maple
text_color = (255, 248, 220)   # Cream/cornsilk

bg_color = (101, 67, 33)       # Dark mahogany
grid_color = (205, 133, 63)    # Medium wood (peru)
text_color = (255, 235, 205)   # Blanched almond
#ui conf
grid_pixel_size = env.tab_size * env.cell_size
window_width = grid_pixel_size
window_height = grid_pixel_size + 100 #extra space for text
FPS = 30

#colors
bg_color = (15, 25, 40)
grid_color = (30, 50, 70)
text_color = (200, 230, 255)


class Display:
    def __init__(self, cmd_queue, display_queue):
        pygame.init()
        self.screen = pygame.display.set_mode((window_width, window_height))  #screen creation
        pygame.display.set_caption("circle of life") #screen title
        self.clock = pygame.time.Clock()
        self.running = True
        
        #queues for comm
        self.cmd_queue = cmd_queue #sending the comms to env
        self.display_queue = display_queue  #receiving frames from env
        
        #actual state of the game
        self.grid_data = bytes([env.empty] * env.number_bytes)
        self.counts = {'grass': 0, 'passive_prey': 0, 'active_prey': 0, 'predator': 0} #counter
        self.raining = False
        self.drought = False
        
        #fonts definition
        self.font = pygame.font.SysFont("Times New Roman", 16, bold=True)
        self.font_small = pygame.font.SysFont("Times New Roman", 14)
        
        #loading the assets
        self.images = {}
        self.load_asset(env.grass, "grass.png", (34, 139, 34))
        self.load_asset(env.passive_prey, "prey.png", (200, 200, 200))
        self.load_asset(env.active_prey, "prey_active.png", (255, 255, 0))
        self.load_asset(env.predator, "predator.png", (220, 20, 60))

    def load_asset(self, key, path, color):
        """load image or create colored squares if it doesn"t load as expected"""
        try:
            img = pygame.image.load(path) #loading img into memory
            self.images[key] = pygame.transform.scale(img, (env.cell_size, env.cell_size)) #resizing the image to the actual size of the cells + saving
        except:
            surf = pygame.Surface((env.cell_size, env.cell_size))
            surf.fill(color)
            pygame.draw.rect(surf, (0, 0, 0), surf.get_rect(), 1) #drawing a border in black
            self.images[key] = surf #saving

    def run(self):
        """main display loop"""
        print("<DISPLAY> starting...")
        
        while self.running:
            #handling events
            for event in pygame.event.get(): #events : mouse click or pressing some keys
                if event.type == pygame.QUIT:
                    self.running = False
                    self.cmd_queue.put("quit") #stopping the simulation
                
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        self.running = False
                        self.cmd_queue.put("quit")
                    
                    elif event.key == pygame.K_SPACE:
                        #drought on/off
                        self.cmd_queue.put("drought")
                    
                    elif event.key == pygame.K_r:
                        #rain on/off
                        self.cmd_queue.put("rain")
            
            #updating the data on the display
            try:
                while True:
                    frame_latest = self.display_queue.get_nowait() #get item: if empty-> it crashes
                    self.grid_data = frame_latest['grid'] #updating data (no previous crash)
                    self.counts = frame_latest['counts']
                    self.raining = frame_latest['raining']
                    self.drought = frame_latest['drought']
            except Empty: #if the crash was cause by an empty queue
                pass #we continue

            #drawing
            self.draw_grid()
            self.draw_ui()
            
            pygame.display.flip() #flipping the buffer: taking everything in the buffer and showing it onto the screen
            self.clock.tick(FPS) #if loop is fast, we cap the execution with a delay

        pygame.quit()

    def draw_grid(self):
        """drawing the grid"""
        self.screen.fill(bg_color) #filling with background color
        
        for i in range(env.number_bytes):
            val = self.grid_data[i] #wholives there

            #calculating 2D position with 1D
            x = (i % env.tab_size) * env.cell_size
            y = (i // env.tab_size) * env.cell_size

            #drawing
            if val in self.images:
                self.screen.blit(self.images[val], (x, y))
            
            #grid lines
            pygame.draw.rect(self.screen, grid_color, (x, y, env.cell_size, env.cell_size), 1) #1 is thickness

    def draw_ui(self):
        """drawing the status panel"""
        y_offset = env.tab_size * env.cell_size #starting position for the panel, where the grid ends
        
        #filling with background color
        pygame.draw.rect(self.screen, (20, 20, 20), (0, y_offset, window_width, 100))
        
        if self.drought:
            status_text = "status: drought -> no grass growth right now"
            status_color = (255, 100, 100)
        elif self.raining:
            status_text = "status: raining -> fast grass growth"
            status_color = (100, 200, 255)
        else:
            status_text = "status: normal"
            status_color = (200, 255, 200)
        
        surf_status = self.font.render(status_text, True, status_color) #rendering the text
        self.screen.blit(surf_status, (10, y_offset + 10)) #pushing the text-image
        
        #counting
        total_prey = self.counts['passive_prey'] + self.counts['active_prey']
        pop_text = (f"grass: {self.counts['grass']}  |  " f"prey: {total_prey}  |  " f"predators: {self.counts['predator']}")
        surf_pop = self.font_small.render(pop_text, True, (200, 200, 200))
        self.screen.blit(surf_pop, (10, y_offset + 40))
        
        # Controls
        controls = "<SPACE> toggle drought  |  <R> toggle rain  |  <ESC> QUIT"
        surf_controls = self.font_small.render(controls, True, (150, 150, 150))
        self.screen.blit(surf_controls, (10, y_offset + 65))


def main(): 
    print("Circle game")
    print("-" * 40)
    print()

    #sync
    grid_lock = multiprocessing.Lock() #mutual exclusion lock creation
    cmd_queue = multiprocessing.Queue() # display-> env
    display_queue = multiprocessing.Queue()  # env ->display

    #env process
    env_proc = env.EnvProcess(grid_lock) #lock to env
    p_env = multiprocessing.Process(target=env_proc.run, args=(cmd_queue, display_queue), daemon=True) #daemon=True for child process, ends when parent process ends
    p_env.start()
    
    #waiting for shared_mem
    time.sleep(1)

    #initial population
    print("spawning initial population...")
    procs = []
    
    #preys
    for _ in range(20):
        p = multiprocessing.Process(target=animals.run_animal, args=(env.passive_prey, grid_lock), daemon=True)
        p.start()
        procs.append(p)

    #predators
    for _ in range(6):
        p = multiprocessing.Process(target=animals.run_animal, args=(env.predator, grid_lock), daemon=True)
        p.start()
        procs.append(p)

    print(f"started {len(procs)} animals")
    print("\ndisplay charging...")

    #running display in the main process(required by pygame)
    display = Display(cmd_queue, display_queue)
    try:
        display.run() #staying here until player quits
    
    except KeyboardInterrupt:
        pass

    finally:
        print("\nshutting down the game and cleaning...")
        p_env.terminate()
        for p in procs:
            if p.is_alive():
                p.terminate()
        
        #cleanup
        try:
            s = shared_memory.SharedMemory(name=env.shared_mem_name)
            s.close()
            s.unlink()
        except:
            pass
        print("cleanup complete")
        sys.exit()


if __name__ == "__main__":
    main()
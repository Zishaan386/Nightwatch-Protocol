"""
NIGHTWATCH PROTOCOL
Standalone VS Code / GitHub version.

No OpenRouter, no API key, no AI model, and no Google Colab dependencies.
The textbox uses a small deterministic command parser.

Put these files in assets/:
    background.png
    tunnel_blueprint.png
    jumpscare.png
    jumpscare.mp3   (or change AUDIO_FILE below)
"""

from pathlib import Path
import random
import re
import sys

import pygame
from PIL import Image


# ============================================================
# PATHS / SETTINGS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = BASE_DIR / "assets"

BACKGROUND_FILE = ASSETS_DIR / "background.png"
MAP_FILE = ASSETS_DIR / "tunnel_blueprint.png"
JUMPSCARE_FILE = ASSETS_DIR / "jumpscare.png"
AUDIO_FILE = ASSETS_DIR / "jumpscare.mp3"

REFERENCE_W = 1402
REFERENCE_H = 1122

# Original monitor calibration from the final game.
UI_REFERENCE = {
    "main_monitor": {"x1": 282, "y1": 429, "x2": 733, "y2": 743},
    "camera_monitor": {"x1": 824, "y1": 482, "x2": 1150, "y2": 738},
}

CAMERAS = {
    "cam 1": "left door",
    "cam 2": "right door",
    "cam 3": "west hall",
    "cam 4": "east hall",
    "cam 5": "stage",
}

MAP_LOCATIONS = {
    "stage":      (0.483, 0.100),
    "west hall":  (0.168, 0.365),
    "east hall":  (0.795, 0.365),
    "dining":     (0.483, 0.505),
    "hallway":    (0.483, 0.375),
    "left door":  (0.263, 0.714),
    "right door": (0.700, 0.714),
    "left hall":  (0.375, 0.724),
    "right hall": (0.592, 0.724),
    "security":   (0.483, 0.724),
}

ROBOT_PATHS = {
    # The building has three broad routes: left, right, and a hidden
    # central route through the hallway/dining area.
    "stage": ["west hall", "east hall", "hallway"],
    "west hall": ["stage", "left door", "dining"],
    "east hall": ["stage", "right door", "dining"],
    "hallway": ["stage", "dining"],
    "dining": ["hallway", "west hall", "east hall"],
    "left door": ["west hall"],
    "right door": ["east hall"],
}

TASK_TEMPLATE = {
    "file_transfer": {
        "name": "Transfer Security Files",
        "goal": 3,
        "power_cost": 4.0,
        "descriptions": [
            "Connecting to the damaged archive server...",
            "Copying encrypted security files...",
            "Verifying transferred files...",
        ],
    },
    "generator": {
        "name": "Restart Backup Generator",
        "goal": 4,
        "power_cost": 5.0,
        "descriptions": [
            "Opening the generator control panel...",
            "Priming the fuel system...",
            "Resetting the generator breaker...",
            "Starting the backup generator...",
        ],
    },
    "wiring": {
        "name": "Repair Wire Connections",
        "goal": 3,
        "power_cost": 4.0,
        "descriptions": [
            "Tracing the damaged cable...",
            "Matching the correct wire connections...",
            "Securing and testing the repaired circuit...",
        ],
    },
}


# ============================================================
# LOAD ASSETS
# ============================================================

def require_file(path: Path, description: str):
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {description}: {path}\n"
            f"Put the file inside the assets folder."
        )


require_file(BACKGROUND_FILE, "background image")
require_file(MAP_FILE, "tunnel blueprint")
require_file(JUMPSCARE_FILE, "jumpscare image")


background_pil = Image.open(BACKGROUND_FILE).convert("RGB")
tunnel_map_pil = Image.open(MAP_FILE).convert("RGB")
jumpscare_pil = Image.open(JUMPSCARE_FILE).convert("RGB")

# Pygame can load PNG/JPG/WEBP through its image module, but using
# PIL first makes asset loading more tolerant.
def pil_to_surface(image):
    return pygame.image.fromstring(image.tobytes(), image.size, image.mode)


# ============================================================
# GAME STATE
# ============================================================

def new_game_state():
    return {
        "active_attacker": None,
        "attack_side": None,
        "minutes": 0,
        "power": 100.0,
        # Counts player actions while monsters are still at the stage.
        "stage_action_count": 0,

        "left_door": False,
        "right_door": False,
        "left_door_auto_open": False,
        "right_door_auto_open": False,

        "camera_active": False,
        "current_camera": None,

        "alive": True,
        "won": False,
        # Guarantees that every normal game has at least one attack attempt.
        "attack_attempted": False,

        "robots": {
            "Bon": {
                "position": "stage",
                "aggression": 0.12,
                "attack_ready": False,
            },
            "Rex": {
                "position": "stage",
                "aggression": 0.08,
                "attack_ready": False,
            },
        },

        "last_camera_result": None,
        "last_event": "Your shift has begun.",
    }


game_state = new_game_state()
memory = []


def remember(event):
    memory.append(str(event))
    if len(memory) > 30:
        memory.pop(0)


def format_time():
    total = game_state["minutes"]
    hour = total // 60
    minute = total % 60
    display_hour = 12 if hour == 0 else hour
    return f"{display_hour}:{minute:02d} AM"


def new_tasks():
    return {
        key: {
            "name": data["name"],
            "progress": 0,
            "goal": data["goal"],
            "completed": False,
            "power_cost": data["power_cost"],
        }
        for key, data in TASK_TEMPLATE.items()
    }


task_state = new_tasks()


def all_tasks_complete():
    return all(task["completed"] for task in task_state.values())


# ============================================================
# GAME MECHANICS
# ============================================================

def begin_new_turn_state():
    """Reset temporary turn effects and handle automatic door opening."""
    # Camera power cost applies only when a camera is checked this turn.
    game_state["camera_active"] = False

    if game_state["left_door_auto_open"]:
        game_state["left_door"] = False
        game_state["left_door_auto_open"] = False

    if game_state["right_door_auto_open"]:
        game_state["right_door"] = False
        game_state["right_door_auto_open"] = False


def check_camera(camera):
    if not game_state["alive"]:
        return "The game is already over."

    if game_state["power"] <= 0:
        return "No power. Cameras are unavailable."

    camera = camera.lower().strip()
    if camera not in CAMERAS:
        return "Invalid camera. Use CAM 1 to CAM 5."

    game_state["power"] = max(0, game_state["power"] - 2)
    game_state["camera_active"] = True

    game_state["current_camera"] = camera

    location = CAMERAS[camera]
    detected = [
        robot
        for robot, data in game_state["robots"].items()
        if data["position"] == location
    ]

    if detected:
        result = (
            f"{camera.upper()}: Movement detected. "
            + ", ".join(detected)
            + " visible."
        )
    else:
        result = f"{camera.upper()}: No movement detected."

    game_state["last_camera_result"] = result
    remember(f"Player checked {camera}: {result}")
    return result


def control_door(door, action):
    door = door.lower().strip()
    action = action.lower().strip()

    if game_state["power"] <= 0:
        return "No power. Doors cannot be controlled."

    if door not in ("left", "right"):
        return "Door must be left or right."

    if action not in ("open", "close"):
        return "Action must be open or close."

    game_state[f"{door}_door"] = action == "close"
    game_state[f"{door}_door_auto_open"] = action == "close"

    remember(f"Player {action}d the {door} door.")
    return f"{door.capitalize()} door {action}d."


def use_intercom(message=""):
    if game_state["power"] <= 0:
        return "The intercom has no power."

    game_state["power"] = max(0, game_state["power"] - 1.5)
    remember(f'Player used intercom: "{message}"')

    # 40% chance to lure a robot one step back toward the stage.
    # This gives the intercom an actual gameplay purpose.
    if random.random() < 0.40:
        candidates = []

        for robot, data in game_state["robots"].items():
            current = data["position"]

            # Do not let the intercom cancel an attack that is already
            # waiting to happen.
            if (
                game_state["active_attacker"] == robot
                and current in ("left door", "right door")
            ):
                continue

   

            if current == "west hall":
                candidates.append((robot, "stage"))
            elif current == "east hall":
                candidates.append((robot, "stage"))
            elif current == "left door":
                candidates.append((robot, "west hall"))
            elif current == "right door":
                candidates.append((robot, "east hall"))
            elif current == "dining":
                candidates.append((robot, "hallway"))
            elif current == "hallway":
                candidates.append((robot, "stage"))

        if candidates:
            robot, destination = random.choice(candidates)
            old_position = game_state["robots"][robot]["position"]
            game_state["robots"][robot]["position"] = destination
            game_state["robots"][robot]["attack_ready"] = False

            if game_state["active_attacker"] == robot and destination not in ("left door", "right door"):
                game_state["active_attacker"] = None

            remember(f"Intercom lured {robot} from {old_position} to {destination}.")
            return (
                "The message echoes through the building. "
                f"You hear {robot} moving away from the office."
            )

        return "The message echoes through the building. Nothing responds."

    return "The message echoes through the building. Nothing obvious happens."


def move_robot(robot):
    if robot not in game_state["robots"]:
        return "Unknown robot."

    data = game_state["robots"][robot]
    current = data["position"]

    if current not in ROBOT_PATHS:
        data["position"] = "stage"
        data["attack_ready"] = False
        current = "stage"

    # A robot already at a door remains the only active attacker.
    if current in ("left door", "right door"):
        game_state["active_attacker"] = robot
        return f"{robot} is waiting at a door zone."

    # After the player has taken 2 actions, any robot still on
    # the stage is forced to leave CAM 5.
    if current == "stage" and game_state["stage_action_count"] >= 2:
        choices = list(ROBOT_PATHS["stage"])

        new_position = random.choice(choices)
        data["position"] = new_position
        data["attack_ready"] = False

        remember(
            f"{robot} was forced to leave the stage and moved to "
            f"{new_position}."
        )

        return f"{robot} left the stage."

    aggression = min(
        0.92,
        data["aggression"] + (game_state["minutes"] / 60) * 0.07,
    )

    if random.random() >= aggression:
        return f"{robot} stayed where it was."

    choices = list(ROBOT_PATHS[current])

    # Only one monster can occupy a door zone at a time.
    active = game_state["active_attacker"]
    if active is not None and active != robot:
        choices = [
            zone for zone in choices
            if zone not in ("left door", "right door")
        ]

    another_at_door = any(
        name != robot and other["position"] in ("left door", "right door")
        for name, other in game_state["robots"].items()
    )

    if another_at_door:
        choices = [
            zone for zone in choices
            if zone not in ("left door", "right door")
        ]

    if not choices:
        return f"{robot} stayed where it was."

    new_position = random.choice(choices)
    data["position"] = new_position
    data["attack_ready"] = False

    if new_position in ("left door", "right door"):
        game_state["active_attacker"] = robot
        remember(f"{robot} entered a door zone.")
    else:
        remember(f"{robot} moved from {current} to {new_position}.")

    return f"{robot} moved."


def random_event():
    events = [
        "You hear metal scraping somewhere in the building.",
        "Something knocks against a wall.",
        "The ventilation system suddenly stops for a few seconds.",
        "You hear footsteps, but cannot tell where they came from.",
        "A camera briefly fills with static.",
    ]

    if random.random() > 0.30:
        return ""

    event = random.choice(events)
    game_state["last_event"] = event
    remember(event)
    return event


def enemy_turn():
    for robot in game_state["robots"]:
        move_robot(robot)

    # Guarantee that the player faces at least one attack attempt
    # before the night can end.
    if (
        not game_state["attack_attempted"]
        and game_state["minutes"] >= 160
        and game_state["active_attacker"] is None
    ):
        robot = random.choice(list(game_state["robots"].keys()))
        side = random.choice(("left", "right"))

        game_state["robots"][robot]["position"] = (
            "left door" if side == "left" else "right door"
        )
        game_state["robots"][robot]["attack_ready"] = False
        game_state["active_attacker"] = robot

        remember(
            f"{robot} was forced toward the "
            f"{side} door as the guaranteed attack attempt."
        )

    return random_event()
def advance_time(minutes=20):
    game_state["minutes"] += minutes

    # Original 20-minute drain.
    drain = 2 / 3

    if game_state["left_door"]:
        drain += 1

    if game_state["right_door"]:
        drain += 1

    if game_state["camera_active"]:
        drain += 1 / 3

    game_state["power"] = max(0, game_state["power"] - drain)
    game_state["camera_active"] = False

    if game_state["power"] <= 0:
        game_state["left_door"] = False
        game_state["right_door"] = False

    remember(
        f"Time advanced to {format_time()}. "
        f"Power: {game_state['power']:.0f}%"
    )


def check_win_loss():
    active_name = game_state["active_attacker"]

    if active_name in game_state["robots"]:
        data = game_state["robots"][active_name]
        position = data["position"]

        if position == "left door" and data["attack_ready"]:
            game_state["attack_attempted"] = True

            if not game_state["left_door"]:
                game_state["alive"] = False
                game_state["attack_side"] = "LEFT"
                game_state["last_event"] = (
                    f"{active_name} attacked through the left door."
                )
                remember(f"{active_name} caught the player from CAM 1.")
                return "LOSE"

            data["position"] = "west hall"
            data["attack_ready"] = False
            game_state["active_attacker"] = None
            remember(
                f"The closed left door blocked {active_name}. "
                "It retreated to CAM 3."
            )

        elif position == "right door" and data["attack_ready"]:
            game_state["attack_attempted"] = True
            if not game_state["right_door"]:
                game_state["alive"] = False
                game_state["attack_side"] = "RIGHT"
                game_state["last_event"] = (
                    f"{active_name} attacked through the right door."
                )
                remember(f"{active_name} caught the player from CAM 2.")
                return "LOSE"

            data["position"] = "east hall"
            data["attack_ready"] = False
            game_state["active_attacker"] = None
            remember(
                f"The closed right door blocked {active_name}. "
                "It retreated to CAM 4."
            )

        elif position not in ("left door", "right door"):
            game_state["active_attacker"] = None

    if game_state["minutes"] >= 360:
        if all_tasks_complete():
            game_state["won"] = True
            return "WIN"

        game_state["alive"] = False
        game_state["last_event"] = (
            "6 AM arrived before all maintenance tasks were completed."
        )
        return "LOSE_TASKS"

    return "CONTINUE"


def do_task(task_name):
    if task_name not in task_state:
        return "Unknown maintenance task."

    task = task_state[task_name]

    if task["completed"]:
        return f'{task["name"]} is already complete.'

    if game_state["power"] <= 0 and task_name != "generator":
        return "There is no power available for that task."

    task["progress"] += 1
    game_state["power"] = max(
        0,
        game_state["power"] - task["power_cost"],
    )

    descriptions = TASK_TEMPLATE[task_name]["descriptions"]
    index = min(task["progress"] - 1, len(descriptions) - 1)
    message = descriptions[index]

    if task["progress"] >= task["goal"]:
        task["completed"] = True

        if task_name == "generator":
            game_state["power"] = min(100, game_state["power"] + 18)
            message += " GENERATOR ONLINE. Power restored by 18%."
        elif task_name == "file_transfer":
            message += " FILE TRANSFER COMPLETE."
        elif task_name == "wiring":
            message += " WIRING REPAIRED."

    remember(
        f'Maintenance: {task["name"]} -> '
        f'{task["progress"]}/{task["goal"]}'
    )
    return message


# ============================================================
# DETERMINISTIC TEXTBOX COMMANDS
# ============================================================

def parse_command(text):
    """
    Returns:
        (function, args, human_response)
    or None if the command is not recognized.
    """
    s = text.lower().strip()

    # Cameras
    match = re.search(r"(?:check|view|look at|open)\s*(?:camera\s*)?(1|2|3|4|5)", s)
    if match or re.fullmatch(r"cam\s*[1-5]", s):
        number = match.group(1) if match else re.search(r"[1-5]", s).group()
        return check_camera, (f"cam {number}",), None

    # Doors
    if "left door" in s:
        action = "close" if any(x in s for x in ("close", "shut")) else "open"
        return control_door, ("left", action), None

    if "right door" in s:
        action = "close" if any(x in s for x in ("close", "shut")) else "open"
        return control_door, ("right", action), None

    # Tasks
    if any(x in s for x in ("transfer security", "transfer files", "security files")):
        return do_task, ("file_transfer",), None

    if any(x in s for x in ("restart generator", "backup generator", "generator")):
        return do_task, ("generator",), None

    if any(x in s for x in ("repair wiring", "fix wiring", "wire connections", "wiring")):
        return do_task, ("wiring",), None

    # Intercom
    if "intercom" in s:
        message = text
        return use_intercom, (message,), None

    # Helpful commands
    if s in ("status", "game status", "check status"):
        return None, (), (
            f"{format_time()} | POWER {game_state['power']:.0f}%\n"
            f"LEFT DOOR: {'CLOSED' if game_state['left_door'] else 'OPEN'}\n"
            f"RIGHT DOOR: {'CLOSED' if game_state['right_door'] else 'OPEN'}"
        )

    if s in ("tasks", "task status", "maintenance"):
        lines = []
        for task in task_state.values():
            status = (
                "DONE"
                if task["completed"]
                else f"{task['progress']}/{task['goal']}"
            )
            lines.append(f"{task['name']}: {status}")
        return None, (), "\n".join(lines)

    if s in ("help", "?"):
        return None, (), (
            "COMMANDS:\n"
            "check cam 1-5\n"
            "close/open left door\n"
            "close/open right door\n"
            "transfer security files\n"
            "restart backup generator\n"
            "repair wire connections\n"
            "use intercom\n"
            "status / tasks"
        )

    return None, (), (
        "COMMAND NOT RECOGNIZED.\n"
        "Type HELP to see available commands."
    )


# ============================================================
# TURN PROCESSING
# ============================================================

def execute_turn(action_function, args=()):
    if not game_state["alive"]:
        return "GAME OVER"

    if game_state["won"]:
        return "YOU ALREADY SURVIVED THE NIGHT."

    # Camera checks are observation only. Intercom also skips the normal
    # enemy movement phase because a successful lure already moves a robot.
    is_observation = action_function == check_camera
    is_intercom_action = action_function == use_intercom
    skip_enemy_movement = is_observation or is_intercom_action

    # Monsters that were already at a door get to attack after this turn.
    door_monsters_before = {
        name
        for name, data in game_state["robots"].items()
        if data["position"] in ("left door", "right door")
    }

    begin_new_turn_state()
    # Count player actions. This is used to prevent monsters from
    # staying on CAM 5 for too long at the beginning of the night.
    game_state["stage_action_count"] += 1
    response = action_function(*args)

    # Camera checks and intercom normally do not trigger enemy movement.
    # However, the second player action must force monsters off CAM 5.
    if skip_enemy_movement and game_state["stage_action_count"] < 2:
        enemy_event = ""
    else:
        enemy_event = enemy_turn()

        # A monster that was already at a door gets its attack turn.
        for name in door_monsters_before:
            if game_state["robots"][name]["position"] in ("left door", "right door"):
                game_state["robots"][name]["attack_ready"] = True

    result = check_win_loss()

    if result == "LOSE":
        return response + "\n\nSomething reaches the office.\n\nYOU WERE CAUGHT."

    advance_time()

    result = check_win_loss()

    if result == "WIN":
        return (
            "6:00 AM\n\n"
            "All maintenance tasks are complete.\n\n"
            "YOU SURVIVED."
        )

    if result == "LOSE_TASKS":
        return (
            "6:00 AM\n\n"
            "Your shift ended, but required maintenance is incomplete.\n\n"
            "YOU LOSE."
        )

    if enemy_event:
        response += "\n\n" + enemy_event

    return response


def process_text_command(text):
    function, args, immediate = parse_command(text)

    if immediate is not None:
        return immediate

    if function is None:
        # Unrecognized text is NOT a turn. This is different from the old
        # LLM version, where every free-form input could be interpreted.
        return "COMMAND NOT RECOGNIZED.\nType HELP to see available commands."

    return execute_turn(function, args)


def reset_game():
    global game_state, memory, task_state
    game_state = new_game_state()
    memory = []
    task_state = new_tasks()


# ============================================================
# PYGAME UI
# ============================================================

pygame.init()

try:
    pygame.mixer.init()
    # Audio is optional; the game still works if jumpscare.mp3 is absent.
    # Audio is optional; the game still works if jumpscare.mp3 is absent.
    AUDIO_AVAILABLE = AUDIO_FILE.exists()
    if AUDIO_AVAILABLE:
        pygame.mixer.music.load(str(AUDIO_FILE))
except pygame.error:
    AUDIO_AVAILABLE = False


GAME_IMAGE_W = 1000
GAME_IMAGE_H = round(1000 * REFERENCE_H / REFERENCE_W)
CONTROL_H = 265
WINDOW_W = GAME_IMAGE_W
WINDOW_H = GAME_IMAGE_H + CONTROL_H

screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
pygame.display.set_caption("Nightwatch Protocol")

clock = pygame.time.Clock()

# Fonts
FONT = pygame.font.SysFont("consolas", 18)
SMALL = pygame.font.SysFont("consolas", 15)
BUTTON_FONT = pygame.font.SysFont("consolas", 15, bold=True)
BIG = pygame.font.SysFont("consolas", 28, bold=True)

GREEN = (70, 255, 100)
DIM_GREEN = (50, 180, 80)
RED = (255, 70, 70)
WHITE = (220, 220, 220)
BLACK = (0, 0, 0)
PANEL = (12, 15, 13)
BUTTON = (30, 45, 32)
BUTTON_HOVER = (45, 70, 48)
BORDER = (75, 130, 85)

background_surface = pil_to_surface(background_pil)
map_surface = pil_to_surface(tunnel_map_pil)
jumpscare_surface = pil_to_surface(jumpscare_pil)

background_surface = pygame.transform.smoothscale(
    background_surface,
    (GAME_IMAGE_W, GAME_IMAGE_H),
)

jumpscare_surface = pygame.transform.smoothscale(
    jumpscare_surface,
    (GAME_IMAGE_W, GAME_IMAGE_H),
)

# Scale the original monitor coordinates to the displayed background.
SX = GAME_IMAGE_W / REFERENCE_W
SY = GAME_IMAGE_H / REFERENCE_H


def scaled_box(name):
    b = UI_REFERENCE[name]
    return (
        int(b["x1"] * SX),
        int(b["y1"] * SY),
        int(b["x2"] * SX),
        int(b["y2"] * SY),
    )


MAIN_BOX = scaled_box("main_monitor")
CAM_BOX = scaled_box("camera_monitor")


# ============================================================
# BUTTON / TEXTBOX HELPERS
# ============================================================

class Button:
    def __init__(self, rect, label, callback):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.callback = callback
        self.enabled = True

    def draw(self, surface):
        mouse = pygame.mouse.get_pos()
        hover = self.rect.collidepoint(mouse)

        color = BUTTON_HOVER if hover and self.enabled else BUTTON
        if not self.enabled:
            color = (25, 25, 25)

        pygame.draw.rect(surface, color, self.rect, border_radius=4)
        pygame.draw.rect(surface, BORDER, self.rect, 1, border_radius=4)

        text_color = GREEN if self.enabled else (80, 80, 80)
        text = BUTTON_FONT.render(self.label, True, text_color)
        surface.blit(
            text,
            (
                self.rect.centerx - text.get_width() // 2,
                self.rect.centery - text.get_height() // 2,
            ),
        )

    def handle(self, event):
        if (
            self.enabled
            and event.type == pygame.MOUSEBUTTONDOWN
            and event.button == 1
            and self.rect.collidepoint(event.pos)
        ):
            self.callback()


input_text = ""
input_active = False
message = (
    "12:00 AM\n\n"
    "Your shift begins. Complete ALL maintenance tasks before 6 AM."
)
show_jumpscare = False
game_finished = False
show_instructions = True


def do_action(function, *args):
    global message, show_jumpscare, game_finished

    if game_finished:
        return

    before = game_state["alive"]
    message = execute_turn(function, args)

    if before and not game_state["alive"]:
        show_jumpscare = game_state["attack_side"] in ("LEFT", "RIGHT")
        game_finished = True
        if show_jumpscare and AUDIO_AVAILABLE:
            try:
                pygame.mixer.music.stop()
                pygame.mixer.music.play()
            except pygame.error:
                pass

    if game_state["won"] or not game_state["alive"]:
        game_finished = True


def camera_action(name):
    do_action(check_camera, name)


def task_action(name):
    do_action(do_task, name)


def toggle_door(side):
    action = "open" if game_state[f"{side}_door"] else "close"
    do_action(control_door, side, action)


def reset_action():
    global message, show_jumpscare, game_finished, input_text, show_instructions

    if AUDIO_AVAILABLE:
        try:
            pygame.mixer.music.stop()
        except pygame.error:
            pass

    reset_game()

    message = (
        "12:00 AM\n\n"
        "Fresh night initialized.\n"
        "Complete every maintenance task before 6 AM."
    )

    show_jumpscare = False
    game_finished = False
    show_instructions = False
    input_text = ""


buttons = []


def build_buttons():
    global buttons
    buttons = []

    y = GAME_IMAGE_H + 35

    

    # Maintenance
    x = 20
    buttons.append(Button((x, y, 210, 34), "TRANSFER FILES",
                          lambda: task_action("file_transfer")))
    x += 220
    buttons.append(Button((x, y, 210, 34), "RESTART GENERATOR",
                          lambda: task_action("generator")))
    x += 220
    buttons.append(Button((x, y, 210, 34), "FIX WIRING",
                          lambda: task_action("wiring")))

    # Doors
    y += 48
    x = 20
    buttons.append(Button((x, y, 210, 34), "LEFT DOOR",
                          lambda: toggle_door("left")))
    x += 220
    buttons.append(Button((x, y, 210, 34), "RIGHT DOOR",
                          lambda: toggle_door("right")))
    x += 220
    buttons.append(Button((x, y, 210, 34), "RESET NIGHT",
                          reset_action))

    # Cameras
    y += 48
    labels = [
        ("CAM 1 - LEFT", "cam 1"),
        ("CAM 2 - RIGHT", "cam 2"),
        ("CAM 3 - WEST", "cam 3"),
        ("CAM 4 - EAST", "cam 4"),
        ("CAM 5 - STAGE", "cam 5"),
    ]

    x = 20
    for label, camera in labels:
        buttons.append(Button(
            (x, y, 170, 34),
            label,
            lambda c=camera: camera_action(c),
        ))
        x += 180


build_buttons()

# Button shown on the jumpscare screen.
play_again_button = Button(
    (
        GAME_IMAGE_W // 2 - 110,
        GAME_IMAGE_H - 75,
        220,
        42,
    ),
    "PLAY AGAIN",
    reset_action,
)

# Exit button shown in the top-right corner.
exit_button = Button(
    (
        GAME_IMAGE_W - 145,
        60,
        125,
        42,
    ),
    "EXIT GAME",
    pygame.quit,
)

# ============================================================
# DRAWING
# ============================================================

def wrap_text(text, font, max_width):
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = word if not current else current + " " + word
        if font.size(test)[0] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def draw_main_monitor(surface, text):
    x1, y1, x2, y2 = MAIN_BOX
    pygame.draw.rect(surface, (3, 12, 6), (x1, y1, x2 - x1, y2 - y1))

    pad = 14
    title = FONT.render("NIGHT SECURITY SYSTEM", True, GREEN)
    surface.blit(title, (x1 + pad, y1 + 12))

    status = FONT.render(
        f"{format_time()}   POWER {game_state['power']:.0f}%",
        True,
        GREEN,
    )
    surface.blit(status, (x1 + pad, y1 + 38))

    left = "CLOSED" if game_state["left_door"] else "OPEN"
    right = "CLOSED" if game_state["right_door"] else "OPEN"
    doors = FONT.render(
        f"L-DOOR:{left}   R-DOOR:{right}",
        True,
        DIM_GREEN,
    )
    surface.blit(doors, (x1 + pad, y1 + 64))

    close = any(
        data["position"] in ("left door", "right door")
        for data in game_state["robots"].values()
    )
    warning = (
        "WARNING: MONSTER CLOSE TO THE OFFICE!"
        if close
        else "PROXIMITY: CLEAR"
    )
    warning_surface = FONT.render(
        warning,
        True,
        RED if close else DIM_GREEN,
    )
    surface.blit(warning_surface, (x1 + pad, y1 + 90))

    pygame.draw.line(
        surface,
        DIM_GREEN,
        (x1 + pad, y1 + 118),
        (x2 - pad, y1 + 118),
        1,
    )

    body_font = SMALL
    max_width = x2 - x1 - pad * 2
    y = y1 + 132

    # Preserve explicit newlines.
    for paragraph in str(text).split("\n"):
        if not paragraph.strip():
            y += 10
            continue

        lines = wrap_text(paragraph, body_font, max_width)

        for line in lines:
            if y + body_font.get_height() > y2 - 10:
                return
            line_surface = body_font.render(line, True, GREEN)
            surface.blit(line_surface, (x1 + pad, y))
            y += body_font.get_height() + 2


def draw_static(surface, rect):
    x, y, w, h = rect
    pygame.draw.rect(surface, (6, 6, 6), rect)

    for _ in range(180):
        px = random.randint(x, x + max(1, w - 1))
        py = random.randint(y, y + max(1, h - 1))
        shade = random.randint(20, 70)
        surface.set_at((px, py), (shade, shade, shade))


def draw_camera_monitor(surface):
    x1, y1, x2, y2 = CAM_BOX
    w = x2 - x1
    h = y2 - y1
    monitor_rect = pygame.Rect(x1, y1, w, h)

    # No power = cameras are dead.
    if game_state["power"] <= 0:
        draw_static(surface, monitor_rect)
        return

    # Always show the tunnel blueprint when power is available.
    map_scaled = pygame.transform.smoothscale(
        map_surface,
        (w, h)
    )

    surface.blit(map_scaled, monitor_rect)
    pygame.draw.rect(surface, BORDER, monitor_rect, 1)

    # Monsters are ONLY visible on the camera the player selected.
    selected = game_state["current_camera"]

    if selected is None:
        return

    visible_zone = CAMERAS.get(selected)

    if visible_zone is None:
        return

    for robot, data in game_state["robots"].items():

        # Monster must physically be inside the selected camera's zone.
        if data["position"] == visible_zone:

            px, py = MAP_LOCATIONS[visible_zone]

            dot_x = x1 + int(px * w)
            dot_y = y1 + int(py * h)

            radius = max(6, int(w * 0.025))

            pygame.draw.circle(
                surface,
                RED,
                (dot_x, dot_y),
                radius
            )

            pygame.draw.circle(
                surface,
                (255, 130, 130),
                (dot_x, dot_y),
                radius,
                2
            )


def draw_tasks(surface):
    x = 700
    y = GAME_IMAGE_H + 22

    title = SMALL.render("MAINTENANCE", True, GREEN)
    surface.blit(title, (x, y))

    y += 23

    for task in task_state.values():
        status = "DONE" if task["completed"] else f"{task['progress']}/{task['goal']}"
        text = SMALL.render(
            f"{task['name']}: {status}",
            True,
            GREEN if task["completed"] else WHITE,
        )
        surface.blit(text, (x, y))
        y += 20


def draw_input(surface):
    global input_active

    rect = pygame.Rect(20, GAME_IMAGE_H + 220, 650, 32)
    pygame.draw.rect(surface, (5, 7, 5), rect)
    pygame.draw.rect(
        surface,
        GREEN if input_active else BORDER,
        rect,
        1,
    )

    shown = input_text[-75:]
    prompt = FONT.render("> " + shown, True, GREEN)
    surface.blit(prompt, (rect.x + 7, rect.y + 5))

    hint = SMALL.render(
        "Type a command, then press ENTER.  HELP = commands.",
        True,
        DIM_GREEN,
    )
    surface.blit(hint, (690, GAME_IMAGE_H + 222))


def draw_jumpscare():
    screen.blit(jumpscare_surface, (0, 0))

    # Exit button in the top-right corner.
    exit_button.draw(screen)

    side = game_state["attack_side"]
    text = BIG.render(
        f"YOU WERE CAUGHT FROM THE {side} SIDE",
        True,
        RED,
    )

    box = text.get_rect(
        center=(GAME_IMAGE_W // 2, GAME_IMAGE_H - 120)
    )

    pygame.draw.rect(
        screen,
        BLACK,
        box.inflate(28, 18),
    )
    screen.blit(text, box)

    # Play Again button
    play_again_button.draw(screen)


def draw_instructions():
    screen.fill(BLACK)

    title = BIG.render("NIGHTWATCH PROTOCOL", True, GREEN)
    screen.blit(
        title,
        title.get_rect(center=(WINDOW_W // 2, 90)),
    )

    lines = [
        "SURVIVE FROM 12:00 AM TO 6:00 AM.",
        "",
        "Complete all 10 maintenance steps before 6 AM.",
        "Every action advances the clock by 20 minutes.",
        "",
        "CAMERAS: Checking a camera reveals a monster only if it is",
        "physically inside that camera's location. Checking cameras",
        "does NOT move the monsters.",
        "",
        "DOORS: Close the matching door when a monster reaches it.",
        "A closed door blocks an attack, but consumes extra power.",
        "",
        "INTERCOM: Sometimes lures a monster one step away.",
        "POWER: Cameras, doors, tasks and time all consume power.",
        "",
        "CAM 1 = LEFT DOOR    CAM 2 = RIGHT DOOR",
        "CAM 3 = WEST HALL   CAM 4 = EAST HALL",
        "CAM 5 = STAGE",
    ]

    y = 155
    for line in lines:
        text = SMALL.render(line, True, WHITE if line else DIM_GREEN)
        screen.blit(text, text.get_rect(center=(WINDOW_W // 2, y)))
        y += 27

    prompt = FONT.render("PRESS ENTER OR SPACE TO START", True, GREEN)
    screen.blit(
        prompt,
        prompt.get_rect(center=(WINDOW_W // 2, WINDOW_H - 55)),
    )


def draw():
    screen.fill(BLACK)

    if show_instructions:
        draw_instructions()
        return

    if show_jumpscare:
        draw_jumpscare()
        return

    screen.blit(background_surface, (0, 0))
    draw_main_monitor(screen, message)
    draw_camera_monitor(screen)

    # Control panel
    pygame.draw.rect(
        screen,
        PANEL,
        (0, GAME_IMAGE_H, WINDOW_W, CONTROL_H),
    )

    pygame.draw.line(
        screen,
        BORDER,
        (0, GAME_IMAGE_H),
        (WINDOW_W, GAME_IMAGE_H),
        2,
    )

    for button in buttons:
        # RESET NIGHT remains usable after winning or losing.
        button.enabled = (button.label == "RESET NIGHT") or not game_finished
        button.draw(screen)

    draw_tasks(screen)
    draw_input(screen)

    # Exit button is always available during the game.
    exit_button.draw(screen)


# ============================================================
# MAIN LOOP
# ============================================================

def main():
    global input_text, input_active, message, show_jumpscare, game_finished, show_instructions

    running = True

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            elif event.type == pygame.KEYDOWN:
                if show_instructions:
                    if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                        show_instructions = False
                    elif event.key == pygame.K_ESCAPE:
                        running = False
                    continue

                if event.key == pygame.K_ESCAPE:
                    running = False

                elif event.key == pygame.K_RETURN:
                    if input_active and not game_finished:
                        command = input_text.strip()
                        input_text = ""
                        if command:
                            message = process_text_command(command)

                            if not game_state["alive"]:
                                # Monster loss.
                                show_jumpscare = (
                                    game_state["attack_side"] in ("LEFT", "RIGHT")
                                )
                                if show_jumpscare and AUDIO_AVAILABLE:
                                    try:
                                        pygame.mixer.music.play()
                                    except pygame.error:
                                        pass

                            if game_state["won"] or not game_state["alive"]:
                                game_finished = True

                elif event.key == pygame.K_BACKSPACE:
                    if input_active:
                        input_text = input_text[:-1]

                else:
                    if input_active and not game_finished:
                        if event.unicode and event.unicode.isprintable():
                            input_text += event.unicode

            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button != 1:
                    continue

                if show_instructions:
                    show_instructions = False
                    continue

                # PLAY AGAIN is handled on the jumpscare screen.
                if show_jumpscare:
                    # EXIT GAME
                    if exit_button.rect.collidepoint(event.pos):
                        pygame.quit()
                        sys.exit()

                    # PLAY AGAIN
                    if play_again_button.rect.collidepoint(event.pos):
                        reset_action()
                        input_active = False

                    continue

                # EXIT GAME during normal gameplay.
                if exit_button.rect.collidepoint(event.pos):
                    pygame.quit()
                    sys.exit()

                # RESET NIGHT is handled even after WIN/LOSE.
                reset_button = next(
                    (b for b in buttons if b.label == "RESET NIGHT"), None
                )

                if (
                    reset_button is not None
                    and reset_button.enabled
                    and reset_button.rect.collidepoint(event.pos)
                ):
                    reset_action()
                    input_active = False
                    continue

                # Input box
                input_rect = pygame.Rect(
                    20,
                    GAME_IMAGE_H + 220,
                    650,
                    32,
                )

                if input_rect.collidepoint(event.pos) and not game_finished:
                    input_active = True
                else:
                    input_active = False

                for button in buttons:
                    if button is not reset_button:
                        button.handle(event)

        draw()
        pygame.display.flip()
        clock.tick(30)

    pygame.quit()


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        pygame.quit()
        print("\nASSET ERROR:")
        print(exc)
        sys.exit(1)

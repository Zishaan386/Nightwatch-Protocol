# NIGHTWATCH PROTOCOL

A standalone survival-horror security game inspired by the classic night-shift survival horror genre.

You are a night security operator trapped inside a facility with hostile robots roaming the building. Your objective is simple:

> **Survive from 12:00 AM to 6:00 AM and complete every required maintenance task.**

Every action matters. Time advances, power is limited, and the robots become increasingly dangerous as the night progresses.

---

## 🎮 Game Overview

**Nightwatch Protocol** is a Python/Pygame-based survival game where you must balance:

* Time
* Power
* Security cameras
* Security doors
* Maintenance tasks
* Robot movement

The game takes place over a single night, starting at **12:00 AM** and ending at **6:00 AM**. To win, you must complete **all 10 maintenance steps** before 6 AM while surviving the robots.

---

## Objective

You must satisfy **both** conditions:
1. Survive until **6:00 AM**
2. Complete all **10 maintenance steps**

If you reach 6 AM without finishing the maintenance work, you lose. If a robot successfully attacks you, you lose immediately.

---

## The Robots

There are two hostile robots: **Bon** and **Rex**. Both begin the night at the **Stage (CAM 5)**.

The robots move independently throughout the facility and their movement becomes more aggressive as time passes. They can travel through:

```text
                    STAGE
                   CAM 5
                  /  |  \
                 /   |   \
          WEST HALL  |  EAST HALL
           CAM 3     |   CAM 4
              \      |      /
               \   DINING /
                  HALLWAY
                /        \
          LEFT DOOR    RIGHT DOOR
            CAM 1        CAM 2
```

* A robot must physically reach a door zone before it can attack.
* Only one robot can occupy a door zone as the active attacker at a time.

---

## Security Cameras

There are five cameras. The camera system works as an observation system; checking a camera does not move the robots.

| Camera | Location |
| :--- | :--- |
| **CAM 1** | Left Door |
| **CAM 2** | Right Door |
| **CAM 3** | West Hall |
| **CAM 4** | East Hall |
| **CAM 5** | Stage |

A robot is only visible when it is physically located in that camera's area **and** you select the corresponding camera.
* *Example:* Robot at West Hall → Select CAM 3 → Robot becomes visible.
* *Example:* Robot at East Hall → Select CAM 3 → No robot visible.

The tunnel blueprint remains visible whenever the cameras have power.

---

## Security Doors

There are two security doors: **Left Door** and **Right Door**.

If a robot reaches a door zone, you must close the corresponding door to block its attack. 
* *Example:* Robot → CAM 1 → LEFT DOOR → Close LEFT DOOR → Attack blocked.

A closed door consumes additional power, so keeping doors closed continuously is dangerous. The correct strategy is to monitor the cameras and close a door when necessary rather than leaving both doors closed all night.

---

## Maintenance Tasks

There are three maintenance objectives containing a total of 10 steps:

1. **Transfer Security Files (3 steps):** 0/3 → 1/3 → 2/3 → 3/3
2. **Restart Backup Generator (4 steps):** 0/4 → 1/4 → 2/4 → 3/4 → 4/4 *(Completing the generator task restores additional power)*
3. **Repair Wire Connections (3 steps):** 0/3 → 1/3 → 2/3 → 3/3

---

## Power System

Power starts at **100%** and is consumed by:
* Performing maintenance
* Checking cameras
* Keeping doors closed
* The normal passage of time

If power reaches 0%, cameras become unavailable, doors automatically open, and you become much more vulnerable to attacks. Power management is an important part of surviving the night.

---

## Time System

The night runs from **12:00 AM** to **6:00 AM**. Every valid player action advances the game clock by 20 minutes (e.g., 12:00 AM → action → 12:20 AM).

Because every action advances time, repeatedly performing actions without considering the robots can quickly bring you closer to 6 AM.

---

## Robot Behavior

* Robots become more aggressive as the night progresses.
* At the beginning of the night, their movement is less frequent, but their probability of moving increases as time passes.
* Robots cannot remain on the Stage indefinitely. After two player actions, any robot still at CAM 5 is forced to leave.
* The game guarantees that an attack attempt will occur during the night, ensuring you must interact with the security system rather than simply completing tasks.

---

## Losing

You lose if:
* **Robot Attack:** A robot reaches a door and successfully attacks while the corresponding door is open. The game displays a jumpscare and identifies the side of the attack (*"YOU WERE CAUGHT FROM THE LEFT/RIGHT SIDE"*).
* **Incomplete Maintenance:** The clock reaches 6:00 AM before all maintenance tasks are completed (*"Your shift ended, but required maintenance is incomplete. YOU LOSE."*).

---

## Winning

You win when it is **6:00 AM**, **all 10 maintenance steps are completed**, and the **player is still alive**.
* The game displays: *"6:00 AM. All maintenance tasks are complete. YOU SURVIVED."*

---

## Controls

The game can be controlled using the UI buttons or the command textbox.

**Camera Commands:**
* `check cam 1` (or simply `cam 1`)
* `check cam 2` (or simply `cam 2`)
* `check cam 3` (or simply `cam 3`)
* `check cam 4` (or simply `cam 4`)
* `check cam 5` (or simply `cam 5`)

**Door Commands:**
* `close left door` / `open left door`
* `close right door` / `open right door`

**Maintenance Commands:**
* `transfer security files`
* `restart backup generator`
* `repair wire connections`

**Information Commands:**
* `status`
* `tasks`
* `help`

---

## Graphical Controls

The bottom control panel provides buttons for all core actions (Transfer Files, Restart Generator, Fix Wiring, Left/Right Doors, CAM 1-5, and Reset Night).
* **EXIT GAME:** Located in the top-right corner.
* **PLAY AGAIN:** Available on the jumpscare screen after being caught.

---

## Requirements

* Python 3.14
* pygame-ce
* Pillow

*Note: The project does not require OpenRouter, API keys, AI models, Google Colab, or an internet connection during gameplay.*

---

## Installation & Structure

**1. Clone the repository and enter the directory:**
```bash
git clone https://github.com/YOUR-USERNAME/Nightwatch-Protocol.git
cd Nightwatch-Protocol
```

**2. Install required packages:**
```bash
pip install -r requirements.txt
```

**3. Project Structure:**
The game expects the required assets to be inside the `assets` folder.
```text
Nightwatch-Protocol/
│
├── main.py
├── requirements.txt
├── README.md
├── .gitignore
│
└── assets/
    ├── background.png
    ├── tunnel_blueprint.png
    ├── jumpscare.png
    └── jumpscare.mp3
```

---

##  Running the Game

From the project directory, run the following to open the Pygame window:
```bash
python main.py
```

---

## Starting a New Night

The **RESET NIGHT** button restarts the game. It resets time (12:00 AM), power (100%), robot positions and states, maintenance progress, and all security systems. Use **PLAY AGAIN** after being caught to immediately start a new night.

---

## Strategy Tips

* **Don't spam maintenance tasks:** Completing tasks quickly is good, but ignoring the robots will result in an attack.
* **Use cameras strategically:** You don't need to constantly check every camera. Focus on areas closest to the office and check the Stage periodically.
* **Watch the doors:** If a robot reaches CAM 1 or CAM 2, be prepared to close the corresponding door.
* **Don't waste power:** Keeping both doors closed continuously drains power quickly.
* **Complete the generator:** This provides additional power, making it crucial for surviving the entire night.
* **Watch the clock:** Plan your work rather than blindly repeating actions.

---

## Technologies Used

* Python 3.14
* Pygame CE
* Pillow
* Regular Expressions
* Deterministic game logic *(instead of an external AI service)*

---

## License

This project is intended as a personal/educational game development project. The code and original assets can be distributed according to the license included with this repository.

**Nightwatch Protocol:** *Watch the cameras. Manage the power. Close the doors. Survive the night.*

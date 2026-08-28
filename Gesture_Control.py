import cv2
import mediapipe as mp
import pyautogui
import math
import tkinter as tk
import threading
import time
import sys

# --- TUNING PARAMETERS ---
PINCH_THRESHOLD_RATIO = 0.16 
SMOOTHING_DOT = 0.18         
FRICTION = 0.70               
SCROLL_SPEED_MODIFIER = 6
EXIT_HOLD_TIME = 0.75  
MOUSE_SMOOTHING = 0.3 # Lower = smoother, Higher = faster
# --------------------

pyautogui.FAILSAFE = False

curr_x, curr_y = 0, 0
hud_mode = "SYSTEM READY" 
running = True 
exit_timer_start = None
left_alt_held = False 
is_active = False 

def on_quit():
    global running
    running = False
    pyautogui.keyUp('alt') 
    pyautogui.mouseUp(button='left')
    try: root.destroy()
    except: pass
    sys.exit()

def tracking_thread():
    global curr_x, curr_y, hud_mode, running, exit_timer_start, left_alt_held, is_active
    
    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(min_detection_confidence=0.7, min_tracking_confidence=0.7)
    cap = cv2.VideoCapture(0)
    sw, sh = pyautogui.size()
    
    prev_y, current_velocity = None, 0
    r_index_active = False
    r_middle_active = False
    r_ring_active = False 
    r_pinky_active = False # New state lock for Right Click

    m_x, m_y = pyautogui.position()

    while cap.isOpened() and running:
        ret, frame = cap.read()
        if not ret: break
        frame = cv2.flip(frame, 1)
        results = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

        palms_detected = False
        right_scroll_active = False

        if results.multi_hand_landmarks and results.multi_handedness:
            if len(results.multi_hand_landmarks) == 2:
                palms_up = sum(1 for h in results.multi_hand_landmarks if all(h.landmark[i].y < h.landmark[i-2].y for i in [8, 12, 16, 20]))
                if palms_up == 2:
                    palms_detected = True
                    if exit_timer_start is None: exit_timer_start = time.time()
                    elapsed = time.time() - exit_timer_start
                    hud_mode = f"OFFLINE IN {max(0, EXIT_HOLD_TIME - elapsed):.1f}s"
                    if elapsed >= EXIT_HOLD_TIME: on_quit()
            
            if not palms_detected: exit_timer_start = None

            for idx, hand_landmarks in enumerate(results.multi_hand_landmarks):
                label = results.multi_handedness[idx].classification[0].label
                l = hand_landmarks.landmark
                palm_size = math.hypot(l[9].x - l[0].x, l[9].y - l[0].y)

                if label == "Left":
                    index_up, pinky_up = l[8].y < l[6].y, l[20].y < l[18].y
                    middle_folded, ring_folded = l[12].y > l[10].y, l[16].y > l[14].y
                    
                    if index_up and pinky_up and middle_folded and ring_folded:
                        if not left_alt_held:
                            pyautogui.keyDown('alt'); pyautogui.press('tab')
                            left_alt_held = True
                            hud_mode = "TASK LINK"
                    else:
                        if left_alt_held:
                            pyautogui.keyUp('alt'); left_alt_held = False
                            hud_mode = "IDLE"

                if label == "Right":
                    # Mouse Positioning
                    curr_x, curr_y = int(l[8].x * sw), int(l[8].y * sh)
                    m_x += (curr_x - m_x) * MOUSE_SMOOTHING
                    m_y += (curr_y - m_y) * MOUSE_SMOOTHING
                    pyautogui.moveTo(int(m_x), int(m_y), _pause=False)

                    dist_idx = math.hypot(l[8].x - l[4].x, l[8].y - l[4].y)
                    dist_mid = math.hypot(l[12].x - l[4].x, l[12].y - l[4].y)
                    dist_ring = math.hypot(l[16].x - l[4].x, l[16].y - l[4].y)
                    dist_pinky = math.hypot(l[20].x - l[4].x, l[20].y - l[4].y)

                    pinch_limit = palm_size * PINCH_THRESHOLD_RATIO

                    if left_alt_held:
                        if dist_idx < pinch_limit:
                            if not r_index_active: pyautogui.press('tab'); r_index_active = True
                        else: r_index_active = False
                        if dist_mid < pinch_limit:
                            if not r_middle_active: pyautogui.hotkey('shift', 'tab'); r_middle_active = True
                        else: r_middle_active = False
                    else:
                        # --- NO-LAG LEFT CLICK HOLD (RING FINGER) ---
                        if dist_ring < pinch_limit:
                            if not r_ring_active:
                                pyautogui.mouseDown(button='left')
                                r_ring_active = True
                            hud_mode = "L-HOLD"
                        else:
                            if r_ring_active:
                                pyautogui.mouseUp(button='left')
                                r_ring_active = False

                        # --- NO-LAG RIGHT CLICK (PINKY FINGER) ---
                        if dist_pinky < pinch_limit:
                            if not r_pinky_active:
                                pyautogui.click(button='right')
                                r_pinky_active = True
                            hud_mode = "R-CLICK"
                        else:
                            r_pinky_active = False

                        # --- SCROLL ACTION ---
                        if dist_idx < pinch_limit:
                            right_scroll_active = True
                            hud_mode = "SCROLLING"
                            if prev_y is not None:
                                current_velocity = (l[8].y * sh - prev_y) * SCROLL_SPEED_MODIFIER
                                pyautogui.scroll(int(current_velocity))
                            prev_y = l[8].y * sh
                        else:
                            if not palms_detected: hud_mode = "ONLINE"
                            prev_y = None
            
            is_active = (left_alt_held or right_scroll_active or palms_detected or r_ring_active)
        else:
            is_active = False

        if not right_scroll_active and abs(current_velocity) > 2.0:
            pyautogui.scroll(int(current_velocity))
            current_velocity *= FRICTION  
        else: current_velocity = 0

    cap.release()

# --- HUD UI (Same as before) ---
root = tk.Tk()
root.overrideredirect(True)
root.attributes("-topmost", True, "-transparentcolor", "black")
root.config(bg="black")
sw_win, sh_win = root.winfo_screenwidth(), root.winfo_screenheight()
root.geometry(f"{sw_win}x{sh_win}+0+0")

canvas = tk.Canvas(root, width=sw_win, height=sh_win, bg="black", highlightthickness=0)
canvas.pack()

b1 = canvas.create_line(0,0,0,0, fill="#00f2ff", width=2)
b2 = canvas.create_line(0,0,0,0, fill="#00f2ff", width=2)
b3 = canvas.create_line(0,0,0,0, fill="#00f2ff", width=2)
b4 = canvas.create_line(0,0,0,0, fill="#00f2ff", width=2)
hud_text = canvas.create_text(0, 0, text="", fill="#00f2ff", font=("OCR A Extended", 9, "bold"), anchor="nw")

s_x, s_y = sw_win//2, sh_win//2
current_size = 10

def update_ui():
    if not running: return
    global s_x, s_y, current_size
    s_x += (curr_x - s_x) * SMOOTHING_DOT
    s_y += (curr_y - s_y) * SMOOTHING_DOT
    
    target_size = 12 if is_active else 18
    current_size += (target_size - current_size) * 0.2
    
    color = "#ff4400" if (left_alt_held or exit_timer_start) else "#00f2ff"
    l_len = current_size * 0.4 
    
    canvas.coords(b1, s_x-current_size, s_y-current_size+l_len, s_x-current_size, s_y-current_size, s_x-current_size+l_len, s_y-current_size)
    canvas.coords(b2, s_x+current_size-l_len, s_y-current_size, s_x+current_size, s_y-current_size, s_x+current_size, s_y-current_size+l_len)
    canvas.coords(b3, s_x+current_size, s_y+current_size-l_len, s_x+current_size, s_y+current_size, s_x+current_size-l_len, s_y+current_size)
    canvas.coords(b4, s_x-current_size+l_len, s_y+current_size, s_x-current_size, s_y+current_size, s_x-current_size, s_y+current_size-l_len)

    for b in [b1, b2, b3, b4]: canvas.itemconfig(b, fill=color)
    canvas.itemconfig(hud_text, text=f"[{hud_mode}]", fill=color)
    canvas.coords(hud_text, s_x + current_size + 10, s_y - 5)
    
    root.after(10, update_ui)

threading.Thread(target=tracking_thread, daemon=True).start()
root.after(10, update_ui)
root.mainloop()
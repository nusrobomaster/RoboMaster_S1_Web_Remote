import pyautogui as pyg
import time

pyg.PAUSE = 0
button_pos = pyg.locateCenterOnScreen("back_button.jpg", confidence=0.9)
pyg.moveTo(button_pos[0], button_pos[1])
pyg.click()

while True:
    pyg.keyDown("w")
    time.sleep(1)
    pyg.keyUp("w")

    pyg.keyDown("a")
    time.sleep(1)
    pyg.keyUp("a")
    
    pyg.keyDown("s")
    time.sleep(1)
    pyg.keyUp("s")
    
    pyg.keyDown("d")
    time.sleep(1)
    pyg.keyUp("d")

    pyg.keyDown("up")
    time.sleep(1)
    pyg.keyUp("up")

    pyg.keyDown("right")
    time.sleep(5)
    pyg.keyUp("right")
    
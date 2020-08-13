import asyncio
import json
import websockets
import sys

import zmq
import cv2
from PIL import Image
import numpy as np

from av import VideoFrame
import pyautogui as pyg

from aiortc import *

robot_connection = None
control_data_channel = None
websocket = None

control_signals = {"w": "w",
                "a": "a",
                "s": "s",
                "d": "d",
                "ArrowUp": "up",
                "ArrowLeft": "left",
                "ArrowDown": "down",
                "ArrowRight": "right"}

pyg.PAUSE = 0
button_pos = pyg.locateCenterOnScreen("back_button.jpg", confidence=0.9)
pyg.moveTo(button_pos[0], button_pos[1])
pyg.click()

async def connect_to_signalling_server(uri, login_message):
    global websocket
    websocket = await websockets.connect(uri)
    print("Connected to server")
    await websocket.send(json.dumps(login_message))

async def recv_message_handler():
    global websocket
    
    await asyncio.sleep(2)

    async for message in websocket:
        data = json.loads(message)
        if data["type"] == "login":
            await login_handler()
        elif data["type"] == "offer":
            await offer_handler(data["offer"], data["name"])
        elif data["type"] == "leave":
            await leave_handler(data["name"])
        else:
            print("Unknown message received from signalling server")

async def login_handler():
    global robot_connection
    global control_data_channel
    global control_signals

    config = RTCConfiguration([\
        RTCIceServer("turn:54.179.2.91:3478", username="RaghavB", credential="RMTurnServer"),\
        RTCIceServer("stun:stun.1.google.com:19302")])

    robot_connection = RTCPeerConnection(configuration=config)

    #turn_pub_context = zmq.Context()
    #turn_pub = turn_pub_context.socket(zmq.PUB)
    #turn_pub.setsockopt(zmq.CONFLATE, 1)
    #turn_pub.setsockopt(zmq.SNDHWM, 100)
    #turn_pub.setsockopt(zmq.RCVHWM, 100)
    #turn_pub.bind("tcp://127.0.0.1:12346")

    #move_pub_context = zmq.Context()
    #move_pub = move_pub_context.socket(zmq.PUB)
    #move_pub.setsockopt(zmq.CONFLATE, 1)
    #move_pub.setsockopt(zmq.SNDHWM, 1)
    #move_pub.setsockopt(zmq.RCVHWM, 1)
    #move_pub.bind("tcp://127.0.0.1:12347")

    #shoot_pub_context = zmq.Context()
    #shoot_pub = shoot_pub_context.socket(zmq.PUB)
    #shoot_pub.setsockopt(zmq.CONFLATE, 1)
    #shoot_pub.bind("tcp://127.0.0.1:12348")

    @robot_connection.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            controls = json.loads(message)
            
            print(controls)            
            
            for key in control_signals:
                if key in controls:
                    pyg.keyDown(control_signals[key])
                else:
                    pyg.keyUp(control_signals[key])

            if "e" in controls:
                pyg.click()

    control_data_channel = robot_connection.createDataChannel("control_data_channel")
    robot_connection.addTrack(S1AppTrack())
    print("RTCPeerConnection object is created")


async def offer_handler(offer, name):
    global websocket
    global robot_connection
    
    await robot_connection.setRemoteDescription(RTCSessionDescription(offer, "offer"))
    answer = await robot_connection.createAnswer()

    await robot_connection.setLocalDescription(answer)
    message = json.dumps({"answer": \
        {"sdp": robot_connection.localDescription.sdp, \
        "type": robot_connection.localDescription.type}, \
        "name": name,
        "type": robot_connection.localDescription.type})
    await websocket.send(message)
    print("Answer sent to " + name)


async def leave_handler(name):
    global robot_connection
    global control_data_channel
    global control_signals

    # Reset keypresses
    for key in control_signals:
        pyg.keyUp(control_signals[key])
    
    print("Closing peer connection to " + str(name))
    # Close peer connection 
    control_data_channel.close()
    await robot_connection.close() 
    await login_handler()


class S1AppTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.sub_context = zmq.Context()
        self.sub = self.sub_context.socket(zmq.SUB)
        self.sub.setsockopt(zmq.CONFLATE, 1)
        self.sub.setsockopt_string(zmq.SUBSCRIBE, "")
        self.is_init = True

        #self.webcam = cv2.VideoCapture("./test.mp4")

    async def recv(self):
        if self.is_init:
            self.sub.connect("tcp://127.0.0.1:12345")
            self.is_init = False

        pts, time_base = await self.next_timestamp()

        raw_bytes = self.sub.recv()

        byte_arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        cv_frame = np.reshape(byte_arr, (720, 1280, 3))

        # Draw crosshair
        center_point = (int(cv_frame.shape[1]/2), int(cv_frame.shape[0]/2))
        cv2.circle(cv_frame, center_point, 3, (255,255,255), thickness=-1)
        cv2.line(cv_frame, (center_point[0],center_point[1]-20), (center_point[0],center_point[1]-40),
                color=(255,255,255), thickness=2) # Up
        cv2.line(cv_frame, (center_point[0],center_point[1]+20), (center_point[0],center_point[1]+40),
                color=(255,255,255), thickness=2) # Down
        cv2.line(cv_frame, (center_point[0]-20,center_point[1]), (center_point[0]-40,center_point[1]), 
                color=(255,255,255), thickness=2) # Left
        cv2.line(cv_frame, (center_point[0]+20,center_point[1]), (center_point[0]+40,center_point[1]), 
                color=(255,255,255), thickness=2) # Right
        #ret, cv_frame = self.webcam.read()

        frame = VideoFrame.from_ndarray(cv_frame, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame


async def main():
    signalling_server_uri = "ws://54.179.2.91:49621"
    if len(sys.argv) == 3:
        signalling_server_uri = "ws://localhost:49621"

    robot_id = sys.argv[1]
    
    await asyncio.gather(    
        connect_to_signalling_server(signalling_server_uri, 
        {"type": "robot-login", 
        "name": robot_id,
        "joinedGame": "battle"}),
        recv_message_handler())


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Exiting")



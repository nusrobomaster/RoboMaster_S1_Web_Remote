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

arena_cam_connection = None
websocket = None

# pyg.PAUSE = 0
# button_pos = pyg.locateCenterOnScreen("back_button.jpg", confidence=0.9)
# pyg.moveTo(button_pos[0], button_pos[1])
# pyg.click()

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
    global arena_cam_connection

    config = RTCConfiguration([\
        # RTCIceServer("turn:54.179.2.91:3478", username="RaghavB", credential="RMTurnServer"),\
        RTCIceServer("stun:stun.1.google.com:19302")])

    arena_cam_connection = RTCPeerConnection(configuration=config)

    arena_cam_connection.addTrack(CamTrack())
    print("RTCPeerConnection object is created")


async def offer_handler(offer, name):
    global websocket
    global robot_connection
    
    await arena_cam_connection.setRemoteDescription(RTCSessionDescription(offer, "offer"))
    answer = await arena_cam_connection.createAnswer()
    
    await arena_cam_connection.setLocalDescription(answer)
    message = json.dumps({"answer": \
        {"sdp": arena_cam_connection.localDescription.sdp, \
        "type": arena_cam_connection.localDescription.type}, \
        "name": name,
        "type": arena_cam_connection.localDescription.type})
    await websocket.send(message)
    print("Answer sent to " + name)


async def leave_handler(name):
    global arena_cam_connection
    
    print("Closing peer connection to " + str(name))
    # Close peer connection 
    await arena_cam_connection.close() 
    await login_handler()


class CamTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.sub_context = zmq.Context()
        self.sub = self.sub_context.socket(zmq.SUB)
        self.sub.setsockopt(zmq.CONFLATE, 1)
        self.sub.setsockopt_string(zmq.SUBSCRIBE, "")
        self.is_init = True
        self.cam = cv2.VideoCapture(0)

    async def recv(self):
        # if self.is_init:
        #     self.sub.connect("tcp://127.0.0.1:12345")
        #     self.is_init = False

        pts, time_base = await self.next_timestamp()

        # raw_bytes = self.sub.recv()

        # byte_arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        # cv_frame = np.reshape(byte_arr, (720, 1280, 3))

        x, cv_frame = self.cam.read()

        cv_frame = cv2.resize(cv_frame, (int(cv_frame.shape[1] / 2), int(cv_frame.shape[0] / 2)))

        frame = VideoFrame.from_ndarray(cv_frame, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame


async def main():
    signalling_server_uri = "ws://54.179.2.91:49621"
    if len(sys.argv) == 3:
        signalling_server_uri = "ws://localhost:49621"

    arena_cam_id = sys.argv[1]
    
    await asyncio.gather(    
        connect_to_signalling_server(signalling_server_uri, 
        {"type": "arena-cam-login", 
        "name": arena_cam_id,
        "joinedGame": "battle"}),
        recv_message_handler())


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Exiting")

import asyncio
import json
import websockets
import sys

import zmq
import cv2
from PIL import Image
import numpy as np

from av import VideoFrame

from aiortc import *

robot_connection = None
control_data_channel = None
websocket = None

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
        else:
            pass

async def login_handler():
    global robot_connection
    global control_data_channel

    config = RTCConfiguration([\
        RTCIceServer("turn:54.179.2.91:3478", username="RaghavB", credential="RMTurnServer"),\
        RTCIceServer("stun:stun.1.google.com:19302")])

    robot_connection = RTCPeerConnection(configuration=config)

    @robot_connection.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            print(message)
            control_data_channel.send("Hi there boi")

    print("RTCPeerConnection object is created")

    control_data_channel = robot_connection.createDataChannel("control_data_channel")
    robot_connection.addTrack(WebcamTrack())


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

class WebcamTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.webcam = cv2.VideoCapture("./test.mp4")
        self.sub_context = zmq.Context()
        self.sub = self.sub_context.socket(zmq.SUB)
        self.sub.setsockopt(zmq.CONFLATE, 1)
        self.sub.setsockopt_string(zmq.SUBSCRIBE, "")
        self.is_init = True

    async def recv(self):
        if self.is_init:
            self.sub.connect("tcp://127.0.0.1:12345")
            self.is_init = False

        pts, time_base = await self.next_timestamp()

        raw_bytes = self.sub.recv()

        byte_arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        cv_frame = np.reshape(byte_arr, (720, 1280, 3))

        frame = VideoFrame.from_ndarray(cv_frame, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame

async def forever_print():
    global control_data_channel
    
    await asyncio.sleep(20)

    print("starting video")
    #cap = cv2.VideoCapture(0)
    #ret, frame = cap.read()
    while True:
        #ret, frame = cap.read()
        #cv2.imshow("Window", frame)
        #cv2.waitKey(1)
        print("Sending data")
        control_data_channel.send("Hi there boi")
        await asyncio.sleep(1)

async def main():
    signalling_server_uri = "ws://localhost:49621"
    robot_id = sys.argv[1]
    
    await asyncio.gather(    
        connect_to_signalling_server(signalling_server_uri, 
        {"type": "robot-login", 
        "name": robot_id,
        "joinedGame": "battle"}),
        recv_message_handler())
        #forever_print())

if __name__ == "__main__":
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

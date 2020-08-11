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
        elif data["type"] == "leave":
            await leave_handler(data["name"])
        else:
            print("Unknown message received from signalling server")

async def login_handler():
    global robot_connection
    global control_data_channel

    config = RTCConfiguration([\
        RTCIceServer("turn:54.179.2.91:3478", username="RaghavB", credential="RMTurnServer"),\
        RTCIceServer("stun:stun.1.google.com:19302")])

    robot_connection = RTCPeerConnection(configuration=config)

    turn_pub_context = zmq.Context()
    turn_pub = turn_pub_context.socket(zmq.PUB)
    turn_pub.setsockopt(zmq.CONFLATE, 1)
    turn_pub.bind("tcp://127.0.0.1:12346")

    move_pub_context = zmq.Context()
    move_pub = move_pub_context.socket(zmq.PUB)
    move_pub.setsockopt(zmq.CONFLATE, 1)
    move_pub.bind("tcp://127.0.0.1:12347")

    @robot_connection.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            controls = json.loads(message)
            
            print(controls)

            # Format is w a s d up left down right space
            move_signal = ['0', '0', '0', '0']
            turn_signal = ['0', '0', '0', '0', '0', '0', '0', '0', '0']
            
            for key in controls:
                if key == "w":
                    move_signal[0] = "1"
                elif key == "a":
                    move_signal[1] = "1"
                elif key == "s":
                    move_signal[2] = "1"
                elif key == "d":
                    move_signal[3] = "1"
                elif key == "ArrowUp":
                    turn_signal[4] = "1"
                elif key == "ArrowLeft":
                    turn_signal[5] = "1"
                elif key == "ArrowDown":
                    turn_signal[6] = "1"
                elif key == "ArrowRight":
                    turn_signal[7] = "1"
                elif key == " ":
                    turn_signal[8] = "1"
            
            move_command = "".join(move_signal)
            turn_command = "".join(turn_signal)

            #for i in range(0, 30):
            #    move_pub.send_string(move_command)
            #    turn_pub.send_string(turn_command)

    print("RTCPeerConnection object is created")

    control_data_channel = robot_connection.createDataChannel("control_data_channel")
    robot_connection.addTrack(S1AppTrack())


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
    
    print("Closing peer connection to " + str(name))
    await robot_connection.close() # Close peer connection 
    control_data_channel = None
    await login_handler()


class S1AppTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        #self.sub_context = zmq.Context()
        #self.sub = self.sub_context.socket(zmq.SUB)
        #self.sub.setsockopt(zmq.CONFLATE, 1)
        #self.sub.setsockopt_string(zmq.SUBSCRIBE, "")
        #self.is_init = True

        self.webcam = cv2.VideoCapture(0)

    async def recv(self):
        #if self.is_init:
        #    self.sub.connect("tcp://127.0.0.1:12345")
        #    self.is_init = False

        pts, time_base = await self.next_timestamp()

        #raw_bytes = self.sub.recv()

        #byte_arr = np.frombuffer(raw_bytes, dtype=np.uint8)
        #cv_frame = np.reshape(byte_arr, (720, 1280, 3))
        ret, cv_frame = self.webcam.read()

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



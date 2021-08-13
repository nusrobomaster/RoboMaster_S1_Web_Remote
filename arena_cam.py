import asyncio
import json
import websockets
import sys

from threading import Semaphore, Thread

import cv2
from PIL import Image
import numpy as np

from av import VideoFrame

from aiortc import *

arena_connection = None
control_data_channel = None
websocket = None

thread_dict = {}
cam = cv2.VideoCapture(0)
cur_frame = None
frameSem = Semaphore()

def cam_func():
    global cam
    global cur_frame
    global frameSem

    while True:    
        # frameSem.acquire()
        ret, cur_frame = cam.read()
        # frameSem.release()

        cv2.imshow("Test", cur_frame)
        cv2.waitKey(1)

camThread = Thread(target=cam_func, daemon=True)
camThread.start()



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

        if data["type"] == "offer":

            config = RTCConfiguration([\
                RTCIceServer("turn:18.142.123.26:3478", username="RaghavB", credential="RMTurnServer"),\
                RTCIceServer("stun:stun.1.google.com:19302")])
            thread_dict[data["name"]] = RTCPeerConnection(configuration=config)
            thread_dict[data["name"]].addTrack(CamTrack())

            print("RTCPeerConnection object is created")

            await thread_dict[data["name"]].setRemoteDescription(RTCSessionDescription(data["offer"], "offer"))
            answer = await thread_dict[data["name"]].createAnswer()

            await thread_dict[data["name"]].setLocalDescription(answer)
            message = json.dumps({"answer": \
                {"sdp": thread_dict[data["name"]].localDescription.sdp, \
                "type": thread_dict[data["name"]].localDescription.type}, \
                "name": data["name"],
                "type": thread_dict[data["name"]].localDescription.type})
            await websocket.send(message)
            print("Answer sent to " +  data["name"])            

        elif data["type"] == "leave":
            print("Closing peer connection to " + str(data["name"]))
            await thread_dict[data["name"]].close()
            del thread_dict[data["name"]]

        else:
            print("Unknown message received from signalling server")


class CamTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()

    async def recv(self):
        global cur_frame
        global frameSem

        pts, time_base = await self.next_timestamp()


        # ret, cv_frame = self.cam.read()
        cv_frame = cv2.resize(cur_frame, (int(1280 / 2), int(720 / 2)))
        cv_frame = cv2.cvtColor(cv_frame, cv2.COLOR_BGR2RGB)

        frame = VideoFrame.from_ndarray(cv_frame, format="rgb24")
        frame.pts = pts
        frame.time_base = time_base
        return frame


async def main():
    signalling_server_uri = "ws://18.142.123.26:49621"
    if len(sys.argv) == 2:
        signalling_server_uri = "ws://localhost:49621"
    
    await asyncio.gather(    
        connect_to_signalling_server(signalling_server_uri, 
        {
            "type": "robot-login", 
            "name": "arena-cam"
        }),
        recv_message_handler())


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("Exiting")



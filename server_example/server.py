import asyncio
import json
import websockets
import sys
import cv2
from PIL import Image

from av import VideoFrame

from aiortc import *

"""
class VideoTransformTrack(MediaStreamTrack):

    kind = "video"

    def __init__(self, track):
        super().__init__()  # don't forget this!
        self.track = track

    async def recv(self):
        frame = await self.track.recv()
        return frame

    @pc.on("iceconnectionstatechange")
    async def on_iceconnectionstatechange():
        log_info("ICE connection state is %s", pc.iceConnectionState)
        if pc.iceConnectionState == "failed":
            await pc.close()
            pcs.discard(pc)

    @pc.on("track")
    def on_track(track):
        log_info("Track %s received", track.kind)

        local_video = VideoTransformTrack(track)
        pc.addTrack(local_video)

        @track.on("ended")
        async def on_ended():
            log_info("Track %s ended", track.kind)
            await recorder.stop()

async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather()
    pcs.clear()
"""

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
        #self.webcam = cv2.VideoCapture(0)

    async def recv(self):
        pts, time_base = await self.next_timestamp()

        #frame = VideoFrame(width=640, height=480)
        ret, cv_frame = self.webcam.read()
        #cv_frame = cv2.cvtColor(cv_frame, cv2.COLOR_BGR2RGB)
        #cv2.imshow("Test window", cv_frame)
        #cv2.waitKey(1)

        #cv_frame = Image.fromarray(cv_frame)
        frame = VideoFrame.from_ndarray(cv_frame, format="bgr24")
        
        #for p in frame.planes:
        #    p.update(bytes(p.buffer_size))
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
    signalling_server_uri = "ws://54.179.2.91:49621"
    robot_id = sys.argv[1]
    
    await asyncio.gather(    
        connect_to_signalling_server(signalling_server_uri, {"type": "login", "name": robot_id}),
        recv_message_handler())
        #forever_print())

if __name__ == "__main__":
    
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

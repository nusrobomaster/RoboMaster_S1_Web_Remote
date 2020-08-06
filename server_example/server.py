import asyncio
import json
import websockets
import sys
import cv2

from av import VideoFrame

from aiortc import *
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder
from aioice.candidate import Candidate
from aiortc.rtcicetransport import candidate_from_aioice

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
        elif data["type"] == "candidate":
            await recv_remote_candidate_handler(data["candidate"])
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

    print("RTCPeerConnection object is created")

    control_data_channel = robot_connection.createDataChannel("control_data_channel")

async def offer_handler(offer, name):
    global websocket
    global robot_connection
    
    await robot_connection.setRemoteDescription(RTCSessionDescription(offer["sdp"], offer["type"]))
    answer = await robot_connection.createAnswer()
    await robot_connection.setLocalDescription(answer)
    message = json.dumps({"answer": \
        {"sdp": robot_connection.localDescription.sdp, \
        "type": robot_connection.localDescription.type}, \
        "name": name,
        "type": robot_connection.localDescription.type})
    await websocket.send(message)
    print("answer sent to " + name)

def parse_candidate(candidateInitDict):
    candpref = 'candidate:'
    candstr = candidateInitDict['candidate']
    if not candstr.startswith(candpref):
            raise ValueError('does not start with proper string')
    candstr = candstr[len(candpref):]
    cand = Candidate.from_sdp(candstr)

    ric = candidate_from_aioice(cand)
    ric.sdpMid = candidateInitDict['sdpMid']
    ric.sdpMLineIndex = candidateInitDict['sdpMLineIndex']
    return ric

async def recv_remote_candidate_handler(candidate):
    global robot_connection
    robot_connection.addIceCandidate(parse_candidate(candidate))

async def forever_print():
    cap = cv2.VideoCapture(0)
    ret, frame = cap.read()
    while ret:
        ret, frame = cap.read()
        cv2.imshow("Window", frame)
        cv2.waitKey(1)
        await asyncio.sleep(0.0001)

async def main():
    await asyncio.gather(
        forever_print(),    
        connect_to_signalling_server(signalling_server_uri, {"type": "login", "name": robot_id}),
        recv_message_handler())

if __name__ == "__main__":
    signalling_server_uri = "ws://54.179.2.91:49621"
    robot_id = sys.argv[1]

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())

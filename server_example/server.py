import argparse
import asyncio
import json
import logging
import os
import ssl
import uuid

import websockets
import sys
import cv2

from aiohttp import web
from av import VideoFrame

from aiortc import *
from aiortc.contrib.media import MediaBlackhole, MediaPlayer, MediaRecorder
from aioice.candidate import Candidate
from aiortc.rtcicetransport import candidate_from_aioice

ROOT = os.path.dirname(__file__)

logger = logging.getLogger("pc")
pcs = set()




class VideoTransformTrack(MediaStreamTrack):
    """
    A video stream track that transforms frames from an another track.
    """

    kind = "video"

    def __init__(self, track):
        super().__init__()  # don't forget this!
        self.track = track

    async def recv(self):
        frame = await self.track.recv()
        return frame

async def offer(request):
    params = await request.json()
    offer = RTCSessionDescription(sdp=params["sdp"], type=params["type"])

    pc = RTCPeerConnection()
    pc_id = "PeerConnection(%s)" % uuid.uuid4()
    pcs.add(pc)

    def log_info(msg, *args):
        logger.info(pc_id + " " + msg, *args)

    log_info("Created for %s", request.remote)

    # prepare local media
    player = MediaPlayer(os.path.join(ROOT, "demo-instruct.wav"))
    if args.write_audio:
        recorder = MediaRecorder(args.write_audio)
    else:
        recorder = MediaBlackhole()

    

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

    # handle offer
    await pc.setRemoteDescription(offer)
    await recorder.start()

    # send answer
    answer = await pc.createAnswer()
    await pc.setLocalDescription(answer)

    return web.Response(
        content_type="application/json",
        text=json.dumps(
            {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        ),
    )

async def on_shutdown(app):
    # close peer connections
    coros = [pc.close() for pc in pcs]
    await asyncio.gather(*coros)
    pcs.clear()

robot_connection = None
control_data_channel = None
websocket = None

async def connect_to_signalling_server(uri, login_message):
    global websocket
    websocket = await websockets.connect(uri)
    await websocket.send(json.dumps(login_message))
    async for message in websocket:
        await recv_message_handler(message)    

async def recv_message_handler(message):
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
    config = RTCConfiguration([\
        RTCIceServer("turn:54.179.2.91:3478", username="RaghavB", credential="RMTurnServer"),\
        RTCIceServer("stun:stun.1.google.com:19302")])

    robot_connection = RTCPeerConnection(configuration=config)

    @robot_connection.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            print(message)
            
    # RtpDataChannels: true is missing
    print("RTCPeerConnection object is created")

    global control_data_channel
    control_data_channel = robot_connection.createDataChannel("control_data_channel")

async def offer_handler(offer, name):
    global websocket
    global robot_connection
    
    await robot_connection.setRemoteDescription(RTCSessionDescription(offer["sdp"], offer["type"]))
    answer = await robot_connection.createAnswer()
    await robot_connection.setLocalDescription(answer)
    print("LOCAL")
    print(robot_connection.localDescription)
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
    # XXX - exists as part of RTCIceParameters
    #ric.usernameFragment = candidateInitDict['usernameFragment']
    return ric

async def recv_remote_candidate_handler(candidate):
    global robot_connection
    my_candy = parse_candidate(candidate)    
    print(my_candy)
    robot_connection.addIceCandidate(my_candy)
    print("candidate added")

async def send_local_candidates():
    global websocket
    global robot_connection
    pass
    #local_candidate_list = robot_connection.__sctp.transport.transport.iceGatherer.getLocalCandidates()
    #print(local_candidate_list)

if __name__ == "__main__":
    signalling_server_uri = "ws://54.179.2.91:49621"
    robot_id = sys.argv[1]

    loop = asyncio.get_event_loop()
    loop.run_until_complete(connect_to_signalling_server(signalling_server_uri, {"type": "login", "name": robot_id}))
    loop.run_forever()
import sys
import asyncio
import socket
import cv2
from PIL import Image as PImage
import numpy as np
import time
import io
import threading
import queue

import json
import websockets

from av import VideoFrame
import libh264decoder

from aiortc import *

from asyncio.events import get_event_loop
sys.path.append('../decoder/ubuntu/output/')
sys.path.append('../../connection/network/')


webrtc_connection = None
websocket = None
control_signals = {"w": "w",
                "a": "a",
                "s": "s",
                "d": "d",
                "ArrowUp": "up",
                "ArrowLeft": "left",
                "ArrowDown": "down",
                "ArrowRight": "right",
                ' ': ' '}
control_data_channel = None

video_socket = None
ctrl_socket = None
decoded_frame_queue = queue.Queue(16)
video_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
ctrl_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
is_shutdown = True

ROBOT_VIDEO_PORT = 40921
ROBOT_CTRL_PORT = 40923
ROBOT_TYPE = 'EP'
    
CHASSIS_DIST_PER_KEY = 0.5
CHASSIS_ANGLE_PER_KEY = 200
GIMBAL_ANGLE_PER_KEY = 200
SERVO_DIST_PER_KEY = 10
ROBOT_MAX_SPEED = 1
ROBOT_MAX_GIMBAL_SPEED = 5
ROBOT_MAX_TURNING_SPEED = 5
ROBOT_GRIPPER_FORCE = 2
ROBOT_MAX_GIMBAL_SPEED = 240


class Robot_Connection(object):
    global video_socket
    global ctrl_socket

    def __init__(self, robot_ip='', computer_port= None):
        self.robot_ip = robot_ip
        self.computer_port = computer_port
        self.control_port = computer_port + 1
        self.ctrl_threads = RobotDataRx()

    def open(self):
        global is_shutdown
        ctrl_socket.settimeout(5)
        try:
            print(self.robot_ip)
            print(ROBOT_CTRL_PORT)
            ctrl_socket.connect((self.robot_ip, ROBOT_CTRL_PORT))
        except Exception as e:
            print('Connection failed, reason is %s' % e)
            return False
        is_shutdown = False
        #self.ctrl_threads.start_ctrl_thread()

    def start_video_recv(self):
        global is_shutdown
        assert not is_shutdown, 'NOT CONNECTED TO CTRL PORT'
        send_data('command')
        time.sleep(1)
        send_data('stream on')
        time.sleep(1)
        if ROBOT_TYPE == 'S1':
            send_data('robot mode gimbal_lead')
            time.sleep(1)
            send_data('gimbal resume')
            time.sleep(1)
            send_data('gimbal recenter')
            time.sleep(1)
        if ROBOT_TYPE == 'EP':
            send_data('robot mode chassis_lead')
            time.sleep(1)
            send_data('robotic_arm recenter')
            time.sleep(1)
            send_data('robotic_gripper open')
            time.sleep(1)

        try:
            video_socket.connect((self.robot_ip, ROBOT_VIDEO_PORT))
        except Exception as e:
            print('Connection failed, %s' % e)
        self.ctrl_threads.start_video_thread()


def send_data(msg):
    msg += ';'
    return ctrl_socket.send(msg.encode('utf-8'))
    
def reset_robot():
    if ROBOT_TYPE == 'S1':
        send_data('robot mode gimbal_lead')
        time.sleep(1)
        send_data('gimbal resume')
        time.sleep(1)
        send_data('gimbal recenter')
        time.sleep(1)
    if ROBOT_TYPE == 'EP':
        send_data('robot mode chassis_lead')
        time.sleep(1)
        send_data('robotic_arm recenter')
        time.sleep(1)
        send_data('robotic_gripper open')
        time.sleep(1)

def control_handler(controls):
    global control_signals
    chassis_x = 0.0
    chassis_y = 0.0
    chassis_z = 0.0
    gimbal_y = 0.0        
    gimbal_p = 0.0
    fire = 0
    #if len(controls) > 0:
    for key in control_signals:
        if key in controls:
            if key == 'w':
                chassis_x += 1
            if key == 's':
                chassis_x -= 1
            if key == 'd':
                chassis_y += 1
            if key == 'a':
                chassis_y -= 1
            if key == 'e':
                chassis_z += 1
            if key == 'q':
                chassis_z -= 1
            if key == 'ArrowRight':
                gimbal_y += 1
            if key == 'ArrowLeft':               
                gimbal_y -= 1
            if key == 'ArrowUp':
                gimbal_p += 1
            if key == 'ArrowDown':
                gimbal_p -= 1
            if key == ' ':
                fire = 1
        
    if ROBOT_TYPE == 'EP':
        chassis_x *= CHASSIS_DIST_PER_KEY
        chassis_y *= CHASSIS_DIST_PER_KEY
        chassis_z *= CHASSIS_ANGLE_PER_KEY
        gimbal_p *= SERVO_DIST_PER_KEY
        gimbal_y *= SERVO_DIST_PER_KEY
        send_data('chassis speed x ' + str(chassis_x) + ' y ' + str(chassis_y) + ' z ' + str(chassis_z))
        send_data('robotic_arm move x ' + str(gimbal_y) + ' y ' + str(gimbal_p))
        if fire:
            send_data('robotic_gripper close ' + str(ROBOT_GRIPPER_FORCE))
        elif not fire:
            send_data('robotic_gripper open ' + str(ROBOT_GRIPPER_FORCE))
    elif ROBOT_TYPE == 'S1':
        chassis_x *= CHASSIS_DIST_PER_KEY
        chassis_y *= CHASSIS_DIST_PER_KEY
        gimbal_y *= GIMBAL_ANGLE_PER_KEY
        gimbal_p *= GIMBAL_ANGLE_PER_KEY
        send_data('chassis speed x ' + str(chassis_x) + ' y ' + str(chassis_y) + ' vxy ' + str(ROBOT_MAX_SPEED))
        send_data('gimbal speed p ' + str(gimbal_p) + ' y ' + str(gimbal_y) + ' vp ' + str(ROBOT_MAX_GIMBAL_SPEED) + ' vy ' + str(ROBOT_MAX_GIMBAL_SPEED))
        if fire:
            send_data('blaster fire')


class RobotDataRx(object):
    def __init__(self):    
        self.video_socket_queue = queue.Queue(32)
        self.video_list = []
        self.video_decoder = libh264decoder.H264Decoder()
        self.video_socket_recv_thread = threading.Thread(target= self._video_socket_recv_task)
        self.video_decoder_thread = threading.Thread(target = self._video_decoder_task)
        #self.ctrl_socket_recv_thread = threading.Thread(target= self._ctrl_socket_recv_task)

    # def start_ctrl_thread(self):
    #     self.ctrl_socket_recv_thread.start()

    def start_video_thread(self):
        self.video_socket_recv_thread.start()
        self.video_decoder_thread.start()

    # def stop_ctrl_thread(self):
    #     self.ctrl_socket_recv_thread.join()
    
    def stop_video_thread(self):
        self.video_socket_recv_thread.join()
        self.video_decoder_thread.join()


    # def _ctrl_socket_recv_task(self):
    #     global ctrl_socket
    #     global is_shutdown
    #     while not is_shutdown:
    #         msg, addr = ctrl_socket.recvfrom(4096)
    #         if msg:
    #             print(msg)

    def _video_socket_recv_task(self):
        global video_socket
        global is_shutdown
        while not is_shutdown:
            msg, addr = video_socket.recvfrom(4096)
            if self.video_socket_queue.full():
                self.video_socket_queue.get()
            self.video_socket_queue.put(msg)

    def _h264_decode(self, packet_data):
        res_frame_list = []
        frames = self.video_decoder.decode(packet_data)
        for framedata in frames:
            (frame, w, h, ls) = framedata
            if frame is not None:
                frame = np.fromstring(frame, dtype=np.ubyte, count=len(frame), sep='')
                frame = (frame.reshape((h, int(ls / 3), 3)))
                frame = frame[:, :w, :]
                res_frame_list.append(frame)
        return res_frame_list
                            


    def _video_decoder_task(self):
        global decoded_frame_queue
        package_data = b''
        while not is_shutdown:
            buff = self.video_socket_queue.get()
            if buff:
                package_data += buff
                if len(buff) != 1460:
                    for frame in self._h264_decode(package_data):
                        try:    
                            image = PImage.fromarray(frame)
                            img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)

                            if decoded_frame_queue.full():
                                decoded_frame_queue.get()
                            decoded_frame_queue.put(img)
                        except Exception as e:
                            if is_shutdown:
                                break
                            print('video decoder queue full')
                            continue
                    package_data=b''


async def get_frames():
    global decoded_frame_queue
    while decoded_frame_queue.qsize() < 1:
        await asyncio.sleep(0)
    return decoded_frame_queue.get()

class RobotVideoTrack(VideoStreamTrack):
    def __init__(self):
        super().__init__()
        self.is_init = False
    

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        img = await get_frames()
        if img is not None:
            center_point = (int(img.shape[1]/2), int(img.shape[0]/2))
            cv2.circle(img, center_point, 3, (255, 255, 255), thickness=-1)
            cv2.line(img, (center_point[0], center_point[1]-20), (center_point[0], center_point[1]-40),
                    color=(255, 255, 255), thickness=2)  # Up
            cv2.line(img, (center_point[0], center_point[1]+20), (center_point[0], center_point[1]+40),
                    color=(255, 255, 255), thickness=2)  # Down
            cv2.line(img, (center_point[0]-20, center_point[1]), (center_point[0]-40, center_point[1]),
                color=(255, 255, 255), thickness=2)  # Left
            cv2.line(img, (center_point[0]+20, center_point[1]), (center_point[0]+40, center_point[1]),
                    color=(255, 255, 255), thickness=2)  # Right
            img = cv2.resize(img, (int(img.shape[1] / 2), int(img.shape[0] / 2)))           
            cv2.imshow('livevew', img)
            cv2.waitKey(1)
            frameOut = VideoFrame.from_ndarray(img, format="rgb24")
            frameOut.pts = pts
            frameOut.time_base = time_base
            return frameOut



###########################################################################################
#       WEBRTC FUNCTIONS

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
    global webrtc_connection
    global control_data_channel
    global control_signals

    config = RTCConfiguration([\
        RTCIceServer("turn:54.179.2.91:3478", username="RaghavB", credential="RMTurnServer"),\
        RTCIceServer("stun:stun.1.google.com:19302")])

    webrtc_connection = RTCPeerConnection(configuration=config)

    @webrtc_connection.on("datachannel")
    def on_datachannel(channel):
        @channel.on("message")
        def on_message(message):
            controls = json.loads(message)
            control_handler(controls)

    control_data_channel = webrtc_connection.createDataChannel("control_data_channel")
    webrtc_connection.addTrack(RobotVideoTrack())
    print("RTCPeerConnection object is created")


async def offer_handler(offer, name):
    global websocket
    global webrtc_connection
    
    await webrtc_connection.setRemoteDescription(RTCSessionDescription(offer, "offer"))
    answer = await webrtc_connection.createAnswer()
    
    await webrtc_connection.setLocalDescription(answer)
    message = json.dumps({"answer": \
        {"sdp": webrtc_connection.localDescription.sdp, \
        "type": webrtc_connection.localDescription.type}, \
        "name": name,
        "type": webrtc_connection.localDescription.type})
    await websocket.send(message)
    print("Answer sent to " + name)


async def leave_handler(name):
    global webrtc_connection
    global control_data_channel
    global control_signals
    print("Closing peer connection to " + str(name))
    # Close peer connection 
    control_data_channel.close()
    await webrtc_connection.close() 
    await login_handler()
    reset_robot()







async def main():
  if len(sys.argv) > 3:
    signalling_server_uri = "ws://18.142.123.26:49621"
    if len(sys.argv) == 4:
        # signalling_server_uri = "ws://localhost:49621"
        robot_id = sys.argv[1]
        robot_ip = sys.argv[2]
        robot_port = int(sys.argv[3])
        robot = Robot_Connection(robot_ip, robot_port)
        robot.open()
        print("Successfully connected to robot")
        robot.start_video_recv()
        await asyncio.gather(    
        connect_to_signalling_server(signalling_server_uri, 
            {"type": "robot-login", 
            "name": robot_id,
            "joinedGame": "battle"}),
            recv_message_handler())
    else:
        print('Pls input robot ID, robot IP and robot port in that order!')




if __name__ == "__main__":
    robot = Robot_Connection
    robot.open
    loop=asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        print('Exiting')

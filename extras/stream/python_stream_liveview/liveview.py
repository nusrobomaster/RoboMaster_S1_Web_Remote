#!python3

import sys
sys.path.append('../decoder/ubuntu/output/')
sys.path.append('../../connection/network/')

import threading
import time
import numpy as np
import libh264decoder
import signal
from PIL import Image as PImage
import cv2
import opus_decoder
import pyaudio
import robot_connection
import enum
import queue


class ConnectionType(enum.Enum):
    WIFI_DIRECT = 1
    WIFI_NETWORKING = 2
    USB_DIRECT = 3


class RobotLiveview(object):
    WIFI_DIRECT_IP = ''
    WIFI_NETWORKING_IP = '192.168.137.181'
    USB_DIRECT_IP = ''
    ROBOT_TYPE = 'S1'
    CHASSIS_DIST_PER_KEY = 1
    CHASSIS_ANGLE_PER_KEY = 5
    GIMBAL_ANGLE_PER_KEY = 5
    SERVO_DIST_PER_KEY = 1
    ROBOT_MAX_SPEED = 1
    ROBOT_MAX_GIMBAL_SPEED = 5
    ROBOT_MAX_TURNING_SPEED = 5
    ROBOT_GRIPPER_FORCE = 2
    ROBOT_MAX_GIMBAL_SPEED = 540
        
    def __init__(self, connection_type):
        self.connection = robot_connection.RobotConnection()
        self.connection_type = connection_type

        self.video_decoder = libh264decoder.H264Decoder()
        libh264decoder.disable_logging()

        # self.audio_decoder = opus_decoder.opus_decoder() 

        self.video_decoder_thread = threading.Thread(target=self._video_decoder_task)
        self.video_decoder_msg_queue = queue.Queue(64)
        #self.video_display_thread = threading.Thread(target=self._video_display_task)

        # self.audio_decoder_thread = threading.Thread(target=self._audio_decoder_task)
        # self.audio_decoder_msg_queue = queue.Queue(32)
        # self.audio_display_thread = threading.Thread(target=self._audio_display_task)

        self.command_ack_list = []

        self.is_shutdown = True

    def open(self):
        if self.connection_type is ConnectionType.WIFI_DIRECT:
            self.connection.update_robot_ip(RobotLiveview.WIFI_DIRECT_IP)
        elif self.connection_type is ConnectionType.USB_DIRECT:
            self.connection.update_robot_ip(RobotLiveview.USB_DIRECT_IP)
        elif self.connection_type is ConnectionType.WIFI_NETWORKING:
            robot_ip = self.WIFI_NETWORKING_IP
            #robot_ip = self.connection.get_robot_ip(timeout=10)  
            if robot_ip:
                self.connection.update_robot_ip(robot_ip)
            else:
                print('Get robot failed')
                return False
        self.is_shutdown = not self.connection.open()
        
    def close(self):
        self.is_shutdown = True
        self.video_decoder_thread.join()
        # self.video_display_thread.join()
        # self.audio_decoder_thread.join()
        # self.audio_display_thread.join()
        self.connection.close()

    def display(self):
        self.command('command')
        time.sleep(1)
        self.command('audio on')
        time.sleep(1)
        self.command('stream on')
        time.sleep(1)
        self.command('stream on')

        self.video_decoder_thread.start()
        #
        #self.audio_decoder_thread.start()
        #self.audio_display_thread.start()

        print('display!')

    def command(self, msg):
        # TODO: TO MAKE SendSync()
        #       CHECK THE ACK AND SEQ
        self.connection.send_data(msg)

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
        package_data = b''

        self.connection.start_video_recv()

        while not self.is_shutdown: 
            buff = self.connection.recv_video_data()
            if buff:
                package_data += buff
                if len(buff) != 1460:
                    for frame in self._h264_decode(package_data):
                        try:
                            #self.video_decoder_msg_queue.put(frame, timeout=2)    
                            image = PImage.fromarray(frame)
                            img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
                            cv2.imshow("Liveview", img)
                            cv2.waitKey(1)
                        except Exception as e:
                            if self.is_shutdown:
                                break
                            print('video decoder queue full')
                            continue
                    package_data=b''

        self.connection.stop_video_recv()

    # def _video_display_task(self):
    #     while not self.is_shutdown: 
    #         try:
    #             frame = self.video_decoder_msg_queue.get(timeout=2)
    #         except Exception as e:
    #             if self.is_shutdown:
    #                 break
    #             print('video decoder queue empty')
    #             continue
    #         image = PImage.fromarray(frame)
    #         img = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    #         cv2.imshow("Liveview", img)
    #         cv2.waitKey(1)


    # def _cmd_send_task(self):
    #     if self.ROBOT_TYPE == 'S1':
    #         robot_connection.send_data('robot mode gimbal_lead')
    #         robot_connection.send_data('gimbal resume')
    #         robot_connection.send_data('gimbal recenter')
    #     if self.ROBOT_TYPE == 'EP':
    #         robot_connection.send_data('robot mode chassis_lead')
    #         robot_connection.send_data('robotic_arm recenter')
    #         robot_connection.send_data('robotic_gripper open')
    #     while not self.is_shutdown:
    #         chassis_x = 0
    #         chassis_y = 0
    #         chassis_z = 0
    #         gimbal_x = 0
    #         gimbal_y = 0
    #         fire = 0
    #         #ctrl_buff =   #get data from web rtc
    #         for key in  control_signals:
    #             if control_signals[key] == 'w':
    #                 chassis_x += 1
    #             if control_signals[key] == 's':
    #                 chassis_x -= 1
    #             if control_signals[key] == 'a':
    #                 chassis_y += 1
    #             if control_signals[key] == 'd':
    #                 chassis_y -= 1
    #             if control_signals[key] == 'e':
    #                 chassis_z += 1
    #             if control_signals[key] == 'q':
    #                 chassis_z -= 1
    #             if control_signals[key] == 'left':
    #                 gimbal_y += 1
    #             if control_signals[key] == 'right':
    #                 gimbal_y -= 1
    #             if control_signals[key] == 'up':
    #                 gimbal_p += 1
    #             if control_signals[key] == 'down':
    #                 gimbal_p -= 1
    #             if control_signals[key] == 'space':
    #                     fire = 1
    #         if self.ROBOT_TYPE == 'EP':
    #             chassis_x *= self.CHASSIS_DIST_PER_KEY
    #             chassis_y *= self.CHASSIS_DIST_PER_KEY
    #             chassis_z *= self.CHASSIS_ANGLE_PER_KEY
    #             gimbal_p *= self.SERVO_DIST_PER_KEY
    #             gimbal_y *= self.SERVO_DIST_PER_KEY
    #             robot_connection.send_data('chassis move x ' + chassis_x + ' y ' + chassis_y + ' z ' + chassis_z + ' vxy ' \
    #             + self.ROBOT_MAX_SPEED + ' vz ' + self.ROBOT_MAX_TURNING_SPEED )
    #             robot_connection.send_data('robotic_arm move x ' + gimbal_y + ' y ' + gimbal_x + ' vy ' + self.ROBOT_MAX_GIMBAL_SPEED)
    #             if fire == 1:
    #                 robot_connection.send_data('robotic_gripper close ' + self.ROBOT_GRIPPER_FORCE)
    #             else if fire == 0:
    #                 robot_connection.send_data('robotic_gripper open ' + self.ROBOT_GRIPPER_FORCE)
    #         else if self.ROBOT_TYPE == 'S1':
    #             chassis_x *= self.CHASSIS_DIST_PER_KEY
    #             chassis_y *= self.CHASSIS_DIST_PER_KEY
    #             gimbal_y *= self.GIMBAL_ANGLE_PER_KEY
    #             gimbal_p *= self.GIMBAL_ANGLE_PER_KEY
    #             robot_connection.send_data('chassis move x ' + chassis_x + ' y ' + chassis_y + ' vxy ' + self.ROBOT_MAX_SPEED + \
    #             ' vz ' + self.ROBOT_MAX_TURNING_SPEED)
    #             robot_connection.send_data('gimbal_move p ' + gimbal_p + ' y ' + gimbal_y + ' vp ' \
    #             + self.ROBOT_MAX_GIMBAL_SPEED + ' vy ' + self.ROBOT_MAX_GIMBAL_SPEED)
    #             if fire:
    #                 robot_connection.send_data('blaster fire')





                    

    # def _audio_decoder_task(self):
    #     package_data = b''

    #     self.connection.start_audio_recv()

    #     while not self.is_shutdown: 
    #         buff = self.connection.recv_audio_data()
    #         if buff:
    #             package_data += buff
    #             if len(package_data) != 0:
    #                 output = self.audio_decoder.decode(package_data)
    #                 if output:
    #                     try:
    #                         self.audio_decoder_msg_queue.put(output, timeout=2)
    #                     except Exception as e:
    #                         if self.is_shutdown:
    #                             break
    #                         print('audio decoder queue full')
    #                         continue
    #                 package_data=b''

    #     self.connection.stop_audio_recv()

    # def _audio_display_task(self):

    #     p = pyaudio.PyAudio()

    #     stream = p.open(format=pyaudio.paInt16,
    #                     channels=1,
    #                     rate=48000,
    #                     output=True)

    #     while not self.is_shutdown: 
    #         try:
    #             output = self.audio_decoder_msg_queue.get(timeout=2)
    #         except Exception as e:
    #             if self.is_shutdown:
    #                 break
    #             print('audio decoder queue empty')
    #             continue
    #         stream.write(output)

    #     stream.stop_stream()
    #     stream.close()


def test():

    robot = RobotLiveview(ConnectionType.WIFI_NETWORKING)

    def exit(signum, frame):
        robot.close()

    signal.signal(signal.SIGINT, exit)
    signal.signal(signal.SIGTERM, exit)

    robot.open()
    robot.display()


if __name__ == '__main__':
    try:
        test()
    except KeyboardInterrupt:
        print('exiting!')

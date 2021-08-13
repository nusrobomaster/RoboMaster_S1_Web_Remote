import queue
import threading
import time
import json
import traceback
import os
import re

import event_client
import rm_ctrl
import rm_define
import rm_log
import tools

import rm_socket

logger = rm_log.dji_scratch_logger_get()

PROTOCAL_MAPPING_TABLE_PATH = os.path.dirname(__file__) + '/protocal_mapping_table.json'

COMMAND_PORT = 40923
PUSH_PORT = 40924
EVENT_PORT = 40925
BROADCAST_PORT = 40926

INADDR_ANY = '0.0.0.0'
WIFI_DIRECT_CONNECTION_IP = '192.168.2.1'

class ProtocalParser(object):
    UART = 'uart'
    NETWORK = 'network'
    def __init__(self, event_dji_system, socket_obj, uart_obj):

        self.event_client = event_dji_system
        self.sdk_ctrl = rm_ctrl.SDKCtrl(event_dji_system)
        self.version = ''

        self.socket_obj = socket_obj
        self.uart_obj = uart_obj
        self.connection_obj = None

        self.command_socket_fd = None
        self.event_socket_fd = None
        self.push_socket_fd = None

        self.remote_host_ip = set()
        self.connection_socket_fd = {}

        self.data_queue = queue.Queue(512)
        self.uart_data_t = ''
        self.socket_data_t = ''

        # make command exec order
        # if there is command has been execed
        # will return error when user send command
        # support 'command1; command2;' to order run many commands
        self.command_execing_event = threading.Event()

        self.command_parser_callback = {
            'command':self.command_protocal_format_parser,
            'version':self.version_protocal_format_parser,
            'quit':self.quit_protocal_format_parser,
        }

        self.data_process_thread = None

        self.protocal_mapping_table = None

        self.sdk_mode = False

        self.ctrl_obj = {}

        self.report_local_host_ip_timer = None

    def init(self, config={}):
        self.config=config

        f = open(PROTOCAL_MAPPING_TABLE_PATH, 'r')
        self.protocal_mapping_table = json.load(f)
        f.close()

        self.command_socket_fd = self.socket_obj.create(
                self.socket_obj.TCP_MODE,
                (INADDR_ANY, COMMAND_PORT),
                server = True,
                recv_msgq_size = 8,
                send_msgq_size = 8,
                connected_callback=self.__command_connected_callback,
                disconnected_callback=self.__command_disconnected_callback,
                )
        if self.command_socket_fd:
            #TODO: handle the error
            logger.info('command socket create successfully.')

        self.event_socket_fd = self.socket_obj.create(
                self.socket_obj.TCP_MODE,
                (INADDR_ANY, EVENT_PORT),
                server = True,
                recv_msgq_size = 8,
                send_msgq_size = 8,
                connected_callback = self.__event_connected_callback
                )
        if self.event_socket_fd:
            logger.info('event socket create successfully.')

        self.push_socket_fd = self.socket_obj.create(
                self.socket_obj.UDP_MODE,
                (INADDR_ANY, PUSH_PORT),
                server = False,
                recv_msgq_size = 1,
                send_msgq_size = 8,
                )
        if self.push_socket_fd:
            logger.info('push socket create successfully.')

        self.broadcast_socket_fd = self.socket_obj.create(
                self.socket_obj.UDP_MODE,
                (INADDR_ANY, BROADCAST_PORT),
                server = False,
                recv_msgq_size = 1,
                send_msgq_size = 8,
                )

        if self.broadcast_socket_fd:
            self.socket_obj.set_udp_default_target_addr(self.broadcast_socket_fd, ('<broadcast>', BROADCAST_PORT))
            logger.info('broadcast socket create successfully.')

        self.ctrl_obj = {}

        if self.report_local_host_ip_timer == None:
            self.report_local_host_ip_timer = tools.get_timer(2, self.report_local_host_ip)
            self.report_local_host_ip_timer.start()

        self.uart_obj.sdk_process_callback_register(self.__uart_command_recv_callback)

    def __event_connected_callback(self, fd, new_fd):
        logger.info('New event connected')
        self.socket_obj.update_socket_info(
                new_fd,
                recv_msgq_size=1,
                send_msgq_size=8,
                )
        if fd not in self.connection_socket_fd.keys():
            self.connection_socket_fd[fd] = []

        self.connection_socket_fd[fd].append(new_fd)

    def __event_recv_callback(self, fd, data):
        pass

    def __event_disconnected_callback(self, fd):
        pass

    def __command_connected_callback(self, fd, new_fd):
        if self.connection_obj == self.uart_obj:
            logger.info('Uart has already connected')
            return
        else:
            logger.info('New command connected')
            self.connection_status_report('connected', fd, new_fd)
            self.socket_obj.update_socket_info(
                    new_fd,
                    recv_msgq_size=8,
                    send_msgq_size=8,
                    recv_callback = self.__command_recv_callback,
                    )

            self.remote_host_ip.add(self.socket_obj.get_remote_host_ip(new_fd))

            if fd not in self.connection_socket_fd.keys():
                self.connection_socket_fd[fd] = []
            self.connection_socket_fd[fd].append(new_fd)

    def __command_recv_callback(self, fd, data):
        if self.connection_obj == self.uart_obj:
            logger.info('Uart has already connected')
            return
        else:
            self.socket_data_t += data
            if ';' in self.socket_data_t:
                data_list = self.socket_data_t.split(';')

                # tail symbal is invalid, whether the data is end of ';' or incomplete command, so pop and save it
                self.socket_data_t = data_list.pop(-1)

                for msg in data_list:
                    self.protocal_parser(fd, msg, self.NETWORK)
            else:
                logger.info('Not found ; in data_list, waitting for next data')
                return

    def __command_disconnected_callback(self, fd):
        self.quit_protocal_format_parser(self.NETWORK, fd, None)
        self.connection_status_report('disconnected', fd, None)

    def __uart_command_recv_callback(self, data):
        logger.info(data)
        if self.connection_obj == self.socket_obj:
            logger.info('Network has already connected')
        else:
            self.uart_data_t += data

            if ';' in self.uart_data_t:
                data_list = self.uart_data_t.split(';')

                # tail symbal is invalid, whether the data is end of ';' or incomplete command, so pop and save it
                self.uart_data_t = data_list.pop(-1)

                logger.info(data_list)
                for msg in data_list:
                    self.protocal_parser(None, msg, self.UART)
            else:
                logger.info('Not found ; in data_list, waitting for next data')
                return

    def command_execing_start(self):
        self.command_execing_event.set()

    def command_execing_is_finish(self):
        self.command_execing_event.is_set()

    def command_execing_finish(self):
        self.command_execing_event.clear()

    def report_local_host_ip(self):
        ip = self.socket_obj.get_local_host_ip()
        if ip and tools.is_station_mode():
            self.socket_obj.send(self.broadcast_socket_fd, 'robot ip %s'%ip)

    def sdk_robot_ctrl(self, ctrl):
        def init():
            self.ctrl_obj['event'] = event_client.EventClient()
            self.ctrl_obj['modulesStatus_ctrl'] = rm_ctrl.ModulesStatusCtrl(self.ctrl_obj['event'])
            self.ctrl_obj['blaster_ctrl'] = rm_ctrl.GunCtrl(self.ctrl_obj['event'])
            self.ctrl_obj['armor_ctrl'] = rm_ctrl.ArmorCtrl(self.ctrl_obj['event'])
            self.ctrl_obj['AI_ctrl'] = rm_ctrl.VisionCtrl(self.ctrl_obj['event'])
            self.ctrl_obj['chassis_ctrl'] = rm_ctrl.ChassisCtrl(self.ctrl_obj['event'])
            self.ctrl_obj['gimbal_ctrl'] = rm_ctrl.GimbalCtrl(self.ctrl_obj['event'])
            self.ctrl_obj['robot_ctrl'] = rm_ctrl.RobotCtrl(self.ctrl_obj['event'], self.ctrl_obj['chassis_ctrl'], self.ctrl_obj['gimbal_ctrl'])
            self.ctrl_obj['led_ctrl'] = rm_ctrl.LedCtrl(self.ctrl_obj['event'])
            self.ctrl_obj['media_ctrl'] = rm_ctrl.MediaCtrl(self.ctrl_obj['event'])
            self.ctrl_obj['mobile_ctrl'] = rm_ctrl.MobileCtrl(self.ctrl_obj['event'])
            self.ctrl_obj['tools'] = rm_ctrl.RobotTools(self.ctrl_obj['event'])
            self.ctrl_obj['sensor_adapter_ctrl'] = rm_ctrl.SensorAdapterCtrl(self.ctrl_obj['event'])
            self.ctrl_obj['ir_distance_sensor_ctrl'] = rm_ctrl.IrDistanceSensorCtrl(self.ctrl_obj['event'])
            self.ctrl_obj['servo_ctrl'] = rm_ctrl.ServoCtrl(self.ctrl_obj['event'])
            self.ctrl_obj['robotic_arm_ctrl'] = rm_ctrl.RoboticArmCtrl(self.ctrl_obj['event'])
            self.ctrl_obj['gripper_ctrl'] = rm_ctrl.RoboticGripperCtrl(self.ctrl_obj['event'])
            self.ctrl_obj['sdk_ctrl'] = rm_ctrl.SDKCtrl(self.ctrl_obj['event'])
            #log_ctrl = rm_ctrl.LogCtrl(event)

        def ready():
            self.ctrl_obj['robot_ctrl'].init()
            self.ctrl_obj['modulesStatus_ctrl'].init()
            self.ctrl_obj['gimbal_ctrl'].init()
            self.ctrl_obj['chassis_ctrl'].init()
            self.ctrl_obj['led_ctrl'].init()
            self.ctrl_obj['blaster_ctrl'].init()
            self.ctrl_obj['mobile_ctrl'].init()
            self.ctrl_obj['servo_ctrl'].init()
            self.ctrl_obj['ir_distance_sensor_ctrl'].init()
            self.ctrl_obj['tools'].init()

            self.ctrl_obj['robot_ctrl'].enable_sdk_mode()
            self.ctrl_obj['robot_ctrl'].set_mode(rm_define.robot_mode_gimbal_follow)
            self.ctrl_obj['chassis_ctrl'].stop()
            self.ctrl_obj['tools'].program_timer_start()

            self.ctrl_obj['AI_ctrl'].sdk_info_push_callback_register(self.AI_info_push_callback)
            self.ctrl_obj['armor_ctrl'].sdk_event_push_callback_register(self.armor_event_push_callback)
            self.ctrl_obj['media_ctrl'].sdk_event_push_callback_register(self.applause_event_push_callback)
            self.ctrl_obj['chassis_ctrl'].sdk_info_push_callback_register(self.chassis_info_push_callback)
            self.ctrl_obj['gimbal_ctrl'].sdk_info_push_callback_register(self.gimbal_info_push_callback)
            self.ctrl_obj['sensor_adapter_ctrl'].sdk_event_push_callback_register(self.io_level_event_push_callback)
            self.ctrl_obj['sdk_ctrl'].sdk_info_push_callback_register(self.youth_competition_msg_push_callback)

        def stop():
            self.ctrl_obj['blaster_ctrl'].stop()
            self.ctrl_obj['chassis_ctrl'].stop()
            self.ctrl_obj['gimbal_ctrl'].stop()
            self.ctrl_obj['media_ctrl'].stop()
            self.ctrl_obj['AI_ctrl'].stop()
            self.ctrl_obj['armor_ctrl'].stop()

        def exit():
            stop()
            self.ctrl_obj['robot_ctrl'].disable_sdk_mode()
            self.ctrl_obj['robot_ctrl'].exit()
            self.ctrl_obj['gimbal_ctrl'].exit()
            self.ctrl_obj['chassis_ctrl'].exit()
            self.ctrl_obj['blaster_ctrl'].exit()
            self.ctrl_obj['mobile_ctrl'].exit()
            self.ctrl_obj['armor_ctrl'].exit()
            self.ctrl_obj['media_ctrl'].exit()
            self.ctrl_obj['sdk_ctrl'].exit()
            self.ctrl_obj['ir_distance_sensor_ctrl'].exit()
            self.ctrl_obj['sensor_adapter_ctrl'].exit()
            self.ctrl_obj['servo_ctrl'].exit()
            self.ctrl_obj['gripper_ctrl'].exit()
            self.ctrl_obj['event'].stop()
            self.ctrl_obj.clear()

        if ctrl == 'init':
            init()
        elif ctrl == 'ready':
            ready()
        elif ctrl == 'stop':
            stop()
        elif ctrl == 'exit':
            exit()

    def __data_process(self):

        self.sdk_robot_ctrl('init')
        self.sdk_robot_ctrl('ready')

        while self.sdk_mode:
            result = False
            try:
                fd, data = self.data_queue.get(timeout=1)
            except queue.Empty:
                continue
            self.command_execing_start()
            if data.req_type == 'set':
                cmd = str(data.obj) + '.' + str(data.function) + str(data.param)

                logger.info(cmd)

                try:
                    result = eval(cmd, self.ctrl_obj)

                except Exception as e:
                    logger.fatal(traceback.format_exc())
                    self.ack(fd, 'fail', data.seq)
                    continue
                if (type(result) == tuple and result[-1] is 0) or (type(result) == bool and result == True) or result == None or result is 0:
                    self.ack(fd, 'ok', data.seq)
                else:
                    self.ack(fd, 'fail', data.seq)
                logger.fatal('process : ' + str(data.obj) + '.' + str(data.function) + str(data.param) + ' exec_result:' + str(result))
            elif data.req_type == 'get':
                if data.param == None:
                    cmd = str(data.obj) + '.' + str(data.function) + '()'
                else:
                    cmd = str(data.obj) + '.' + str(data.function) + str(data.param)

                logger.info(cmd)

                try:
                    result = eval(cmd, self.ctrl_obj)

                except Exception as e:
                    logger.fatal(traceback.format_exc())
                    self.ack(fd, 'fail', data.seq)
                seq = data.seq
                data = ''
                if type(result) == tuple or type(result) == list:
                    for i in result:
                        if type(i) == float:
                            data = data + '%.3f'%i + ' '
                        else:
                            data = data + str(i) + ' '
                else:
                    data = str(result) + ' '
                self.ack(fd, data, seq)
            else:
                time.sleep(0.05)
            self.command_execing_finish()

        self.sdk_robot_ctrl('exit')

    def protocal_parser(self, fd, data, mode=None):
        #command
        logger.info('Recv string: %s'%(data))
        command = data.split(' ')

        if len(command) == 0:
            return

        # find 'seq'
        seq = None
        if 'seq' in command:
            seq_pos = command.index('seq')
            if len(command) > seq_pos+1:
                seq = command[seq_pos+1]
                if seq.isdigit():
                    seq = int(seq)
                elif re.match(r'^0x[0-9a-fA-F]+$', seq):
                    seq = int(seq, 16)
                else:
                    self.ack(fd, 'command format error: seq parse error')
            else:
                self.ack(fd, 'command format error: no seq value')
            command = command[0:seq_pos]

        if self.command_execing_is_finish():
            self.ack(fd, 'error', seq)
            return False

        # check protocal format
        command_obj = command[0]

        # call process function
        if command_obj in self.command_parser_callback.keys():
            result = self.command_parser_callback[command_obj](mode, fd, seq)
            if result == False or result == None:
                self.ack(fd, '%s exec error'%command_obj, seq)
            elif result == True:
                self.ack(fd, 'ok', seq)
            else:
                self.ack(fd, result, seq)
        else:
            if not self.sdk_mode:
                self.ack(fd, 'not in sdk mode', seq)
                return False
            result = self.ctrl_protocal_format_parser(command, seq)
            if result == False or result == None:
                self.ack(fd, 'command format error: command parse error', seq)
            else:
                if not self.data_queue.full():
                    try:
                        self.data_queue.put_nowait((fd, result))
                    except Exception as e:
                        # full ?
                        logger.fatal(e)

    def command_protocal_format_parser(self, mode, fd, seq):
        if self.sdk_mode == False:
            self.sdk_mode = True
            if self.data_process_thread == None or self.data_process_thread.is_alive() == False:
                self.data_process_thread = threading.Thread(target=self.__data_process)
                self.data_process_thread.start()

            if self.report_local_host_ip_timer and self.report_local_host_ip_timer.is_start():
                self.report_local_host_ip_timer.join()
                self.report_local_host_ip_timer.stop()

            if mode == self.UART:
                self.connection_obj = self.uart_obj
                self.uart_data_t = ''
            elif mode == self.NETWORK:
                self.connection_obj = self.socket_obj
                self.socket_data_t = ''

            return True
        else:
            return 'Already in SDK mode'

    def version_protocal_format_parser(self, mode, fd, seq):
        if 'version' in self.config.keys():
            return 'version ' + self.config['version']

    def quit_protocal_format_parser(self, mode, fd, seq):
        if self.data_process_thread and self.data_process_thread.is_alive():
            if self.report_local_host_ip_timer == None:
                self.report_local_host_ip_timer = tools.get_timer(2, self.connection_obj.report_local_host_ip)
                self.report_local_host_ip_timer.start()
            else:
                self.report_local_host_ip_timer.start()
            self.sdk_mode = False
            self.data_process_thread.join()
            self.ack(fd, 'ok', seq)
            if mode:
                self.connection_obj = None
                self.socket_data_t = ''
                self.uart_data_t = ''
            return True
        else:
            self.ack(fd, 'quit sdk mode failed', seq)
            if mode:
                self.connection_obj = None
            return False

    def ctrl_protocal_format_parser(self, command, seq):
        cmdpkg = CommandPackage()
        cmdpkg.seq = seq

        try:
            # get object
            obj = command[0]
            if obj in self.protocal_mapping_table.keys():
                cmdpkg.obj = self.protocal_mapping_table[obj]['obj']
            else:
                logger.error('obj parse error')
                return False

            # get function key
            function = command[1]
            if function in self.protocal_mapping_table[obj]['functions'].keys():
                function_dict = self.protocal_mapping_table[obj]['functions'][function]

                # check if get command
                if '?' in command:
                    params_list = command[2:]
                    if '?' in params_list:
                        params_list.remove('?')
                    cmdpkg.function = function_dict['get'][0]
                    cmdpkg.req_type = 'get'
                    params = []

                    '''
                    if len(function_dict['get'][1:]) != 0 and len(params_list) != 0:
                        cmdpkg.param = tuple(params_list[0:len(function_dict['get'][1:])])
                    '''

                    for param in function_dict['get'][1:]:
                        # handle the first param is status bit
                        if len(function_dict['get'][1:]) == 1:
                            value = None
                            if len(params_list) == 0:
                                value = None
                            elif len(params_list) == 1:
                                value = params_list[0]
                            elif params_list[0] == function_dict['get'][1:][0]:
                                value = params_list[1]
                            if value and value.isdigit():
                                value = int(value)
                            elif re.match(r'^0x[0-9a-fA-F]+$', value):
                                value = int(value, 16)
                            elif value == 'True' or value == 'true':
                                value = True
                            elif value == 'False' or value == 'false':
                                value = False
                            else:
                                try:
                                    value = float(value)
                                except Exception as e:
                                    pass
                            params.append(value)
                            break

                        # check params
                        if param in params_list and params_list.index(param) + 1 < len(params_list):
                            value = params_list[params_list.index(param)+1]
                            if value and value.isdigit():
                                value = int(value)
                            elif re.match(r'^0x[0-9a-fA-F]+$', value):
                                value = int(value, 16)
                            elif value == 'True' or value == 'true':
                                value = True
                            elif value == 'False' or value == 'false':
                                value = False
                            else:
                                try:
                                    value = float(value)
                                except Exception as e:
                                    pass
                            params.append(value)
                        else:
                            params.append(None)

                    cmdpkg.param = tuple(params)
                    logger.info(cmdpkg.param)

                # set command
                else:
                    # get params list
                    params_list = command[2:]
                    cmdpkg.function = function_dict['set'][0]
                    cmdpkg.req_type = 'set'
                    params = []

                    for param in function_dict['set'][1:]:
                        # handle the first param is status bit
                        if len(function_dict['set'][1:]) == 1:
                            value = None
                            if len(params_list) == 0:
                                value = None
                            elif len(params_list) == 1:
                                value = params_list[0]
                            elif len(params_list) == 2:
                                value = params_list[1]
                            if value and value.isdigit():
                                value = int(value)
                            elif value and re.match(r'^0x[0-9a-fA-F]+$', value):
                                value = int(value, 16)
                            elif value == 'True' or value == 'true':
                                value = True
                            elif value == 'False' or value == 'false':
                                value = False
                            else:
                                try:
                                    value = float(value)
                                except Exception as e:
                                   pass
                            params.append(value)
                            break

                        # check params
                        if param in params_list and params_list.index(param) + 1 < len(params_list):
                            value = params_list[params_list.index(param)+1]
                            if value.isdigit():
                                value = int(value)
                            elif re.match(r'^0x[0-9a-fA-F]+$', value):
                                value = int(value, 16)
                            elif value == 'True' or value == 'true':
                                value = True
                            elif value == 'False' or value == 'false':
                                value = False
                            else:
                                try:
                                    value = float(value)
                                except Exception as e:
                                    pass
                            params.append(value)
                        else:
                            params.append(None)

                    cmdpkg.param = tuple(params)
                    logger.info(cmdpkg.param)
            else:
                logger.error('function key parse error')
                return False
        except Exception as e:
            logger.fatal(traceback.format_exc())
            return False

        return cmdpkg

    def connection_status_report(self, status, fd, data):
        logger.info('connect status changed, local host ip info : %s remote host ip info: %s, cur status: %s'%(self.socket_obj.get_local_host_ip(data), self.socket_obj.get_remote_host_ip(data), status))
        mode = 'wifi'
        if data != None:
            ip = self.socket_obj.get_local_host_ip(data)
            if ip ==  tools.get_ip_by_dev_name('wlan0'):
                mode = 'wifi'
            elif ip ==  tools.get_ip_by_dev_name('rndis0'):
                mode = 'rndis'
            logger.info('connect mode: %s'%(mode))

        if status == 'connected':
            self.sdk_ctrl.sdk_on(mode)
        elif status == 'disconnected':
            self.sdk_ctrl.sdk_off()

    def armor_event_push_callback(self, event):
        if len(event) == 0:
            return

        msg ='armor event'
        if 'hit' in event.keys():
            msg += ' hit %d %d ;'%(event['hit'])
        self.send('event', msg)

    def applause_event_push_callback(self, event):
        if len(event) == 0:
            return

        msg = 'sound event'
        if 'applause' in event.keys():
            msg += ' applause %d ;'%(event['applause'])
        self.send('event',  msg)

    def io_level_event_push_callback(self, event):
        if len(event) == 0:
            return

        msg = 'sensor_adapter event'
        if 'io_level' in event.keys():
            msg += ' io_level %d ;'%(event['io_level'])
        self.send('event',  msg)

    def chassis_position_info_push_callback(self, x, y):
        pass

    def chassis_info_push_callback(self, info):
        if len(info) == 0:
            return

        msg = 'chassis push'
        if 'position' in info.keys():
            msg += ' position %.3f %.3f ;'%(info['position'])
        if 'attitude' in info.keys():
            msg += ' attitude %.3f %.3f %.3f ;'%(info['attitude'])
        if 'status' in info.keys():
            msg += ' status %d %d %d %d %d %d %d %d %d %d %d ;'%(info['status'])
        self.send('push',  msg)

    def gimbal_info_push_callback(self, info):
        if len(info) == 0:
            return

        msg = 'gimbal push'
        if 'attitude' in info.keys():
            msg += ' attitude %.3f %.3f ;'%(info['attitude'])
        self.send('push',  msg)

    def AI_info_push_callback(self, info):
        if len(info) == 0:
            return
        msg = 'AI push'
        if 'people' in info.keys():
            msg += ' people %d'%len(info['people'])
            for i in info['people']:
                msg += ' %.3f %.3f %.3f %.3f'%(i.pos.x, i.pos.y, i.size.w, i.size.h)
        if 'pose' in info.keys():
            msg += ' pose %d'%len(info['pose'])
            for i in info['pose']:
                msg += ' %d %.3f %.3f %.3f %.3f'%(i.info, i.pos.x, i.pos.y, i.size.w, i.size.h)
        if 'marker' in info.keys():
            msg += ' marker %d'%len(info['marker'])
            for i in info['marker']:
                msg += ' %d %.3f %.3f %.3f %.3f'%(i.info, i.pos.x, i.pos.y, i.size.w, i.size.h)
        if 'line' in info.keys():
            msg += ' line %d'%int(len(info['line'])/10)
            for i in info['line']:
                msg += ' %.3f %.3f %.3f %.3f'%(i.pos.x, i.pos.y, i.size.w, i.size.h)
        if 'robot' in info.keys():
            msg += ' robot %d'%len(info['robot'])
            for i in info['robot']:
                msg += ' %.3f %.3f %.3f %.3f'%(i.pos.x, i.pos.y, i.size.w, i.size.h)

        self.send('push', msg)

    def gimbal_status_info_push_callback(self):
        pass

    def youth_competition_msg_push_callback(self, info):
        if len(info) == 0:
            logger.error('SYS_GAME : msg is none')
            return
        msg = 'game msg push '
        if 'data' in info['game_msg'].keys():
            msg += str(info['game_msg']['data'])
        self.send('push', msg)

    def ack(self, fd, data, seq=None):
        msg = data
        if seq != None:
            msg += ' seq %s'%(str(seq))

        msg += ';'

        if self.connection_obj:
            self.connection_obj.send(fd, msg)

    def req(self):
        pass

    def send(self, obj, data):
        fd = None

        data += ';'

        if self.connection_obj == self.uart_obj:
            self.connection_obj.send(None, data)
        else:
            if obj == 'command':
                if self.connection_obj:
                    return self.connection_obj.send(self.command_socket_fd, data)
                else:
                    return None
            elif obj == 'event':
                logger.info(self.connection_socket_fd)
                for user_fd in self.connection_socket_fd[self.event_socket_fd]:
                    if self.connection_obj:
                        self.connection_obj.send(user_fd, data)
                return 0
            elif obj == 'push':
                for ip in self.remote_host_ip:
                    if self.connection_obj:
                        self.connection_obj.send(self.push_socket_fd, data, (ip, PUSH_PORT))
                return 0
            else:
                return None

    def recv(self):
        pass

class CommandPackage(object):
    def __init__(self):
        self.obj = None
        self.function = None
        self.param = None
        self.seq = None
        self.req_type = None

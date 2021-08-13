import os
import plaintext_sdk

class SDKManager(object):
    def __init__(self, event_client, socket_obj, uart_obj):
        self.plaintext_sdk = plaintext_sdk.PlaintextSDK(event_client, socket_obj, uart_obj)
        self.plaintext_sdk_config = {}
        self.load_cfg()

    def load_cfg(self):

        # load version
        cur_dir = os.path.dirname(__file__)
        f = open(cur_dir + '/version.txt')
        version_ori = f.readlines()
        f.close()

        version=''
        for i in version_ori:
            version = version + '%.2d.'%int(i.split(' ')[-1][0:-1])

        version=version[0:-1]

        self.plaintext_sdk_config['version'] = version

    def enable_plaintext_sdk(self):
        self.plaintext_sdk.init(self.plaintext_sdk_config)

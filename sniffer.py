import zmq
import cv2
import time
import numpy as np

subContext = zmq.Context()
sub = subContext.socket(zmq.SUB)
sub.setsockopt_string(zmq.SUBSCRIBE, "")
sub.connect("tcp://127.0.0.1:12345")



while (1):
    raw_bytes = sub.recv()
    
    byte_arr = np.frombuffer(raw_bytes, dtype=np.uint8)

    img_matrix = np.reshape(byte_arr, (720, 1280, 3))
    img_matrix = cv2.cvtColor(img_matrix, cv2.COLOR_BGR2RGB)

    cv2.imshow("display", img_matrix)
    cv2.waitKey(1)
    

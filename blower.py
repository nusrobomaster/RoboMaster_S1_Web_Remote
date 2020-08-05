import zmq

pubContext = zmq.Context()
pub = pubContext.socket(zmq.PUB)
pub.bind("tcp://127.0.0.1:12346")

cont_sends = 30

while True:
    inputCmd = str(input())
    #inputCmd = "d"
    command = ""

    if inputCmd == "w":
        command = "up"
    elif inputCmd == "s":
        command = "down"
    elif inputCmd == "a":
        command = "left"
    elif inputCmd == "d":
        command = "right"
    else:
        print("Invalid command entered!")
        continue
    
    print("Sending command: " + command)

    for i in range(0, cont_sends):
        pub.send_string(command)
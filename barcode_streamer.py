# Use of a CSI camera and pyzbar library to read barcodes and QR codes
# stream real-time at a specified ip address and a specified port
# usage:
# python3 barcode_streamer.py --ip 0.0.0.0 --port 8888 

import cv2
from flask import Response
from flask import Flask
from flask import render_template
import threading
import argparse
import time
from pyzbar import pyzbar


""" 
initialize the output frame and a lock used to ensure thread-safe exchanges 
of the output frames (useful for multiple browswers/tabs are viewing the stream)

"""

outputFram = None
lock = threading.Lock()
"""
// for continuous hosting of webpage.
"""

#initialize a flask object
app = Flask(__name__) 
"""
// create a flask object
"""

@app.route("/") 
def index():
    # return the rendered template
    return render_template("index.html")

"""
// load index.html at endpoint uri call
"""

""" 
gstreamer_pipeline returns a GStreamer pipeline for capturing from the CSI camera
Flip the image by setting the flip_method (most common values: 0 and 2)
display_width and display_height determine the size of each camera pane in the window on the screen
Default 1920x1080 displayd in a 1/4 size window
"""

def gstreamer_pipeline(
    sensor_id=0,
    capture_width=1920,
    capture_height=1080,
    display_width=960,
    display_height=540,
    framerate=30,
    flip_method=0,
):
    return (
        "nvarguscamerasrc sensor-id=%d !"
        "video/x-raw(memory:NVMM), width=(int)%d, height=(int)%d, framerate=(fraction)%d/1 ! "
        "nvvidconv flip-method=%d ! "
        "video/x-raw, width=(int)%d, height=(int)%d, format=(string)BGRx ! "
        "videoconvert ! "
        "video/x-raw, format=(string)BGR ! appsink"
        % (
            sensor_id,
            capture_width,
            capture_height,
            framerate,
            flip_method,
            display_width,
            display_height,
        )
    )
"""
// scan for barcode in the frame and identify barcode location
"""

# To flip the image, modify the flip_method parameter (0 and 2 are the most common)
print(gstreamer_pipeline(flip_method=0))
video_capture = cv2.VideoCapture(gstreamer_pipeline(flip_method=0), cv2.CAP_GSTREAMER)
time.sleep(2.0) 


def barcode_reader():
    # WM global references to the output frame and the lock vairable. 
    global video_capture, outputFrame, lock

    window_title = "Barcode Reader"

    if video_capture.isOpened():
        try:
            window_handle = cv2.namedWindow(window_title, cv2.WINDOW_AUTOSIZE)
            while True:
                ret_val, frame = video_capture.read()
                barcodes = pyzbar.decode(frame)
                # Check to see if the user closed the window
                # Under GTK+ (Jetson Default), WND_PROP_VISIBLE does not work correctly. Under Qt it does
                # GTK - Substitute WND_PROP_AUTOSIZE to detect if window has been closed by user
                if cv2.getWindowProperty(window_title, cv2.WND_PROP_AUTOSIZE) >= 0:
                    cv2.imshow(window_title, frame)
                else:
                    break 

                frame_count = 1
                for barcode in barcodes:
                    frame_count = frame_count+1 
                    (x,y,w,h) = barcode.rect
                    cv2.rectangle(frame,(x,y),(x+w,y+h),(0,0,255),2)
                    barcodeData = barcode.data.decode("utf-8")
                    barcodeType = barcode.type
                    print(barcodeData)
                    text = "{} ({})".format(barcodeData, barcodeType)
                    cv2.putText(frame,text,(x,y-10), cv2.FONT_HERSHEY_SIMPLEX,0.5,(0,0,255),2)
                    cv2.imshow(window_title,frame)
                with lock:
                    outputFrame = frame.copy()
                
                keyCode = cv2.waitKey(30) & 0xFF
                # Stop the program on the ESC key or 'q'
                if keyCode == 27 or keyCode == ord('q'):
                    break
        finally:
            video_capture.release()
            cv2.destroyAllWindows()
    else:
        print("Error: Unable to open camera")

def generate():
    # global references to the output frame and the lock variables
    global outputFrame, lock
    # loop over frames from the output stream
    while True:
        # wait until the lock is acquired
        with lock:
            # check if the output frame is available otherwise skip
            if outputFrame is None:
                continue
            # encode the frame in JPEG format
            (flag, encodedImage) = cv2.imencode(".jpg", outputFrame)
            # ensure the frame is successfully encoded
            if not flag:
                continue
        # yield the output frame in the byte format
        yield(b'--frame\r\n' b'Content-Type: image/jpeg\r\n\r\n' + bytearray(encodedImage) + b'\r\n')

@app.route("/video_feed")
def video_feed():
    #return the reponse generated along with the specified medial 
    # type (mime type)
    return Response(generate(), mimetype = "multipart/x-mixed-replace; boundary=frame")

# check to see if this is the main thread of execution
if __name__ =='__main__':
    # construct the argument parser and pass commandline arguments
    ap = argparse.ArgumentParser()
    ap.add_argument("-i","--ip",action='store',dest='ip',help="ip address of the Jetson Nano") 
    ap.add_argument("-o","--port",action = 'store', dest='port',help="ephermeral port number of the stream server (1024 to 65535)") 
    ap.add_argument("--width",dest='image_width', help="image width [1920]", default=1920, type=int) 
    ap.add_argument("--height",dest='image_height',help="image height [1080]", default=1080, type=int)
    args = ap.parse_args()

    # start the thread that will perform barcode reading
    t = threading.Thread(target=barcode_reader)
    t.daemon = True
    t.start()

    # start the flask app
    app.run(host=args.ip,port=args.port, debug=True, threaded=True, use_reloader = False)
    # app.run(host="192.168.50.80", port=8000, debug=True, threaded=True, use_reloader=False)
 


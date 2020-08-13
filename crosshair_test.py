import cv2

cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)
ret, cv_frame = cap.read()

while ret:
    ret, cv_frame = cap.read()

    center_point = (int(cv_frame.shape[1]/2), int(cv_frame.shape[0]/2))
    cv2.circle(cv_frame, center_point, 3, (255,255,255), thickness=-1)
    cv2.line(cv_frame, (center_point[0],center_point[1]-20), (center_point[0],center_point[1]-40),
            color=(255,255,255), thickness=2) # Up
    cv2.line(cv_frame, (center_point[0],center_point[1]+20), (center_point[0],center_point[1]+40),
            color=(255,255,255), thickness=2) # Down
    cv2.line(cv_frame, (center_point[0]-20,center_point[1]), (center_point[0]-40,center_point[1]), 
            color=(255,255,255), thickness=2) # Left
    cv2.line(cv_frame, (center_point[0]+20,center_point[1]), (center_point[0]+40,center_point[1]), 
            color=(255,255,255), thickness=2) # Right
    
    cv2.imshow("Video", cv_frame)
    cv2.waitKey(1)
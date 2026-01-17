import cv2
import numpy as np
import json

def process_frame_for_qr(image_bytes):
    try:
        # Convert bytes to numpy array
        nparr = np.frombuffer(image_bytes, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return []

        # Detect QR Codes
        detector = cv2.QRCodeDetector()
        retval, decoded_info, points, _ = detector.detectAndDecodeMulti(frame)
        
        qr_results = []
        if retval:
            points = points.astype(int)
            for i, text in enumerate(decoded_info):
                if text:
                    # Convert numpy int32 to python int for JSON serialization
                    bbox = points[i].tolist() 
                    qr_results.append({
                        "text": text,
                        "bbox": bbox
                    })
        return qr_results
    except Exception as e:
        print(f"CV Process Error: {e}")
        return []

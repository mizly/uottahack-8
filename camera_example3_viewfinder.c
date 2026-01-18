/*
 * Copyright (c) 2024, BlackBerry Limited. All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <stdio.h>
#include <unistd.h>
#include <stdlib.h>
#include <string.h>
#include <signal.h>
#include <errno.h>
#include <camera/camera_api.h>

// Frame Header Structure
// Total Size: 24 bytes
typedef struct {
    double timestamp;   // 8 bytes (ms)
    uint32_t size;      // 4 bytes
    uint32_t width;     // 4 bytes
    uint32_t height;    // 4 bytes
    uint32_t format;    // 4 bytes (camera_frametype_t)
} __attribute__((packed)) FrameHeader;

volatile sig_atomic_t g_running = 1;

void handle_signal(int sig) {
    g_running = 0;
}

/**
 * @brief Callback function invoked when a new frame is available.
 * 
 * @param handle Camera handle
 * @param buf Pointer to the camera buffer containing the new frame
 * @param arg User defined argument passed during callback registration
 */
void viewfinder_callback(camera_handle_t handle, camera_buffer_t* buf, void* arg) {
    if (!g_running || !buf || !buf->framebuf) {
        return;
    }

    // Determine width/height/size based on frame type
    uint32_t width = 0;
    uint32_t height = 0;
    uint32_t payload_size = 0;
    
    // Check common formats
    if (buf->frametype == CAMERA_FRAMETYPE_NV12) {
        width = buf->framedesc.nv12.width;
        height = buf->framedesc.nv12.height;
        // NV12 Size = Y Plane + UV Plane
        // Often stride * height * 1.5, but safer to use offsets if available.
        // Simplified: stride * height + stride * (height/2)
        payload_size = buf->framedesc.nv12.stride * height + buf->framedesc.nv12.stride * (height / 2);
    } else if (buf->frametype == CAMERA_FRAMETYPE_RGB8888 || buf->frametype == CAMERA_FRAMETYPE_BGR8888) {
        // Structs are identical
        width = buf->framedesc.rgb8888.width;
        height = buf->framedesc.rgb8888.height;
        payload_size = buf->framedesc.rgb8888.stride * height;
    } else {
         // Fallback - try NV12 accessors (dangerous but existing code did this)
         width = buf->framedesc.nv12.width;
         height = buf->framedesc.nv12.height;
         // Guessing 4 bytes per pixel if unknown, or 0 to be safe?
         // Let's default to 0 and skip writing if unknown
         payload_size = 0;
    }

    if (payload_size == 0) {
        // Skip unknown formats
        return;
    }

    FrameHeader header;
    header.timestamp = (double)(buf->frametimestamp) / 1000.0; // Convert us to ms
    header.size = payload_size;
    header.width = width;
    header.height = height;
    header.format = (uint32_t)buf->frametype;

    // Write header
    if (fwrite(&header, sizeof(FrameHeader), 1, stdout) != 1) {
        g_running = 0;
        return;
    }

    // Write frame data
    if (fwrite(buf->framebuf, 1, payload_size, stdout) != payload_size) {
         g_running = 0;
         return;
    }
    
    // Flush to ensure immediate delivery
    fflush(stdout);
}


int main(int argc, char *argv[])
{
    int                 err;
    camera_handle_t     cameraHandle = CAMERA_HANDLE_INVALID;

    // Setup signal handling
    signal(SIGINT, handle_signal);
    signal(SIGTERM, handle_signal);
    // Ignore SIGPIPE to avoid tearing down immediately if reader closes, 
    // though fwrite err checking handles it.
    signal(SIGPIPE, SIG_IGN); 

    // Open first camera
    err = camera_open(CAMERA_UNIT_1, CAMERA_MODE_RW, &cameraHandle);
    if (err != EOK) {
        fprintf(stderr, "Failed to open camera: %s\n", strerror(err));
        return -1;
    }

    // Start viewfinder with callback
    // We pass NULL for status callback and arg
    err = camera_start_viewfinder(cameraHandle, viewfinder_callback, NULL, NULL);
    if (err != EOK) {
        fprintf(stderr, "Failed to start viewfinder: %s\n", strerror(err));
        camera_close(cameraHandle);
        return -1;
    }

    // Output basic info to stderr (so it doesn't pollute stdout stream)
    fprintf(stderr, "Camera started. Streaming to stdout...\n");

    // Main loop
    while (g_running) {
        usleep(100000); // Sleep 100ms
    }

    fprintf(stderr, "\nStopping camera...\n");

    // Cleanup
    camera_stop_viewfinder(cameraHandle);
    camera_close(cameraHandle);

    return 0;
}

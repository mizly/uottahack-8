#include <Arduino.h>
#include <math.h>
#include <Servo.h>

/* =====================================================
   ================= STEPPER CONFIG ====================
   ===================================================== */

const int StepX = 2;
const int DirX  = 5;
const int StepY = 3;
const int DirY  = 6;
const int StepZ = 4;
const int DirZ  = 7;
const int StepA = A0;
const int DirA  = A1;

const int MAX_SPEED = 127;
const int BASE_STEP_DELAY = 200; // µs

const int StepPins[4] = {StepX, StepY, StepZ, StepA};
const int DirPins[4]  = {DirX,  DirY,  DirZ,  DirA};

int counters[4] = {0, 0, 0, 0};

/* =====================================================
   ================= SERVO CONFIG ======================
   ===================================================== */

const int PAN_SERVO_PIN  = A3;
const int TILT_SERVO_PIN = A5;

const bool INVERT_PAN  = true;
const bool INVERT_TILT = false;

const int PAN_MIN  = 0;
const int PAN_MAX  = 180;
const int TILT_MIN = 20;
const int TILT_MAX = 160;

// Maximum degrees the servo will move PER update loop when joystick is at full deflection
// Tweak these two values to control how fast the gimbal responds.
const float PAN_STEP_MAX_DEG  = 0.2; // degrees per loop at full joystick deflection
const float TILT_STEP_MAX_DEG = 0.2; // degrees per loop at full joystick deflection

const int TRIG_DEADZONE = 8; // small deadzone for triggers to avoid tiny unintended rotations

const int JOY_DEADZONE = 8;

Servo panServo;
Servo tiltServo;

// Current servo angles (kept as floats for smooth incremental updates)
float currentPan = 90.0;
float currentTilt = 90.0;

/* =====================================================
   ================= CONTROLLER STATE ==================
   ===================================================== */

int8_t lx = 0, ly = 0, rx = 0, ry = 0;
uint8_t lt = 0, rt = 0;
uint16_t buttons = 0;

/* =====================================================
   ================= SETUP =============================
   ===================================================== */

void setup() {
  for (int i = 0; i < 4; i++) {
    pinMode(StepPins[i], OUTPUT);
    pinMode(DirPins[i], OUTPUT);
  }

  panServo.attach(PAN_SERVO_PIN);
  tiltServo.attach(TILT_SERVO_PIN);

  // Ensure starting angles are within configured limits
  currentPan = constrain(currentPan, PAN_MIN, PAN_MAX);
  currentTilt = constrain(currentTilt, TILT_MIN, TILT_MAX);

  panServo.write((int)currentPan);
  tiltServo.write((int)currentTilt);

  Serial.begin(115200);
}

/* =====================================================
   ================= MAIN LOOP =========================
   ===================================================== */

void loop() {
  readControllerPacket();

  // ---- LEFT STICK → STEPPERS ----
  int* speeds = holonomicXDrive(
      vectorToAngle(lx, ly),
      vectorMagnitude(lx, ly)
  );
  setMotorSpeeds(speeds);

  // ---- RIGHT STICK → SERVOS ----
  updateGimbalFromJoystick();
}

/* =====================================================
   ================= STEPPER LOGIC =====================
   ===================================================== */

int* holonomicXDrive(float angleDeg, float magnitude) {
  static int motorSpeeds[4];

  float rad = angleDeg * PI / 180.0;

  float fl = sin(rad + PI/4) * magnitude;
  float fr = sin(rad - PI/4) * magnitude;
  float bl = sin(rad - PI/4) * magnitude;
  float br = sin(rad + PI/4) * magnitude;

  float maxVal = max(max(abs(fl), abs(fr)), max(abs(bl), abs(br)));
  if (maxVal > MAX_SPEED) {
    float scale = MAX_SPEED / maxVal;
    fl *= scale; fr *= scale; bl *= scale; br *= scale;
  }

  motorSpeeds[0] = (int)br; // BR
  motorSpeeds[1] = (int)fl; // FL
  motorSpeeds[2] = (int)fr; // FR
  motorSpeeds[3] = (int)bl; // BL

  return motorSpeeds;
}

void setMotorSpeeds(int speeds[4]) {
  // Simple flat trigger-based adjustment:
  // left trigger adds a flat positive value to each motor, right trigger subtracts a flat value.
  // triggerAdd = (lt - rt) / 255 * ROTATION_MAX_SPEED
  if (lt > TRIG_DEADZONE) {
    speeds[0] += lt;
    speeds[1] -= lt;
    speeds[2] += lt;
    speeds[3] -= lt;
  }

  if (rt > TRIG_DEADZONE) {
    speeds[0] -= rt;
    speeds[1] += rt;
    speeds[2] -= rt;
    speeds[3] += rt;
  }

    // Explicitly clamp to allowed range immediately after trigger adjustment
    for (int i = 0; i < 4; i++) {
      if (speeds[i] > MAX_SPEED) speeds[i] = MAX_SPEED;
      if (speeds[i] < -MAX_SPEED) speeds[i] = -MAX_SPEED;
    }

  // Existing direction inversion for motor wiring
  speeds[1] *= -1;
  speeds[3] *= -1;

  for (int i = 0; i < 4; i++) {
    speeds[i] = constrain(speeds[i], -MAX_SPEED, MAX_SPEED);
    digitalWrite(DirPins[i], speeds[i] >= 0 ? HIGH : LOW);
    counters[i] += abs(speeds[i]);

    if (counters[i] >= MAX_SPEED) {
      digitalWrite(StepPins[i], HIGH);
      counters[i] -= MAX_SPEED;
    }
  }

  delayMicroseconds(2);

  for (int i = 0; i < 4; i++) {
    digitalWrite(StepPins[i], LOW);
  }

  delayMicroseconds(BASE_STEP_DELAY);
}

float vectorToAngle(int x, int y) {
  if (x == 0 && y == 0) return 0.0;
  float angle = atan2(-y, x) * 180.0 / PI;
  if (angle < 0) angle += 360.0;
  return angle;
}

float vectorMagnitude(int x, int y) {
  return sqrt((float)x * x + (float)y * y);
}

/* =====================================================
   ================= SERVO LOGIC =======================
   ===================================================== */

void updateGimbalFromJoystick() {
  int panJoy  = INVERT_PAN  ? -rx : rx;
  int tiltJoy = INVERT_TILT ? -ry : ry;
  if (abs(panJoy) < JOY_DEADZONE) panJoy = 0;
  if (abs(tiltJoy) < JOY_DEADZONE) tiltJoy = 0;

  // Scale joystick (-127..127) to a per-loop degree delta based on configured max step
  float panDelta  = (panJoy  / 127.0) * PAN_STEP_MAX_DEG;
  float tiltDelta = (tiltJoy / 127.0) * TILT_STEP_MAX_DEG;

  currentPan  = constrain(currentPan  + panDelta,  PAN_MIN,  PAN_MAX);
  currentTilt = constrain(currentTilt + tiltDelta, TILT_MIN, TILT_MAX);

  panServo.write((int)round(currentPan));
  tiltServo.write((int)round(currentTilt));
}


/* =====================================================
   ================= SERIAL INPUT ======================
   ===================================================== */

void readControllerPacket() {
  if (Serial.available() < 8) return;

  uint8_t buf[8];
  Serial.readBytes(buf, 8);

  lx = (int8_t)buf[0];
  ly = (int8_t)buf[1];
  rx = (int8_t)buf[2];
  ry = (int8_t)buf[3];

  // Keep triggers as raw 0..255 values for smooth analog scaling
  lt = buf[4];
  rt = buf[5];

  buttons = ((uint16_t)buf[6] << 8) | buf[7];
}

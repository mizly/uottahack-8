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
const int BASE_STEP_DELAY = 600; // µs

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

const int JOY_DEADZONE = 8;

Servo panServo;
Servo tiltServo;

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

  panServo.write(90);
  tiltServo.write(90);

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

  panServo.write(mapJoystickToServo(panJoy,  PAN_MIN,  PAN_MAX));
  tiltServo.write(mapJoystickToServo(tiltJoy, TILT_MIN, TILT_MAX));
}

int mapJoystickToServo(int joy, int minA, int maxA) {
  if (abs(joy) < JOY_DEADZONE) joy = 0;
  return constrain(map(joy, -127, 127, minA, maxA), minA, maxA);
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

  lt = map(buf[4], 0, 255, 0, 127);
  rt = map(buf[5], 0, 255, 0, 127);

  buttons = ((uint16_t)buf[6] << 8) | buf[7];
}

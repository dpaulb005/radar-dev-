/*
 * rx_node_ftm.ino — OPTIONAL accuracy upgrade (time-of-flight ranging).
 *
 * Requires an FTM-capable chip on BOTH ends: ESP32-S2/S3/C3/C6.
 * (Original ESP32-WROOM chips do not support 802.11mc FTM.)
 *
 * The node associates with the drone's hidden softAP (drone_beacon.ino
 * enables the FTM responder on it) and runs a burst of FTM exchanges
 * every RANGE_MS, printing the measured distance as JSON over its own
 * USB serial port:
 *
 *   {"node":1,"dist":4.37,"rtt_ns":29,"t":123456}
 *
 * Unlike the RSSI sniffers, each FTM node plugs into the laptop
 * directly (pass extra --port arguments to locate.py). FTM needs no
 * RSSI calibration — the distance comes from round-trip time.
 *
 * Note: this mode is two-way (the node transmits to the drone), so it
 * trades the receive-only property of rx_node for ~0.5-2 m accuracy.
 */

#include <WiFi.h>

// ---------------- configuration ----------------
#define NODE_ID          1            // UNIQUE per node
#define FTM_SSID         "drone-ftm"  // must match drone_beacon.ino
#define FTM_PASS         "ftmftmftm"
#define RANGE_MS         500          // one FTM burst every 500 ms
#define FTM_FRAME_COUNT  16           // frames per burst: 8/16/24/32
#define FTM_BURST_PERIOD 2            // *100 ms between bursts
// -----------------------------------------------

#if !SOC_WIFI_FTM_SUPPORT
#error "This chip does not support WiFi FTM. Use ESP32-S2/S3/C3/C6, or the RSSI rx_node firmware."
#endif

static SemaphoreHandle_t ftmDone;
static volatile bool     ftmOk   = false;
static volatile float    distM   = 0;
static volatile uint32_t rttNs   = 0;

static void onFtmReport(arduino_event_t *event) {
  wifi_event_ftm_report_t *report = &event->event_info.wifi_ftm_report;
  ftmOk = (report->status == FTM_STATUS_SUCCESS);
  if (ftmOk) {
    distM = report->dist_est / 100.0f;  // dist_est is in cm
    rttNs = report->rtt_est;
    free(report->ftm_report_data);
  }
  xSemaphoreGive(ftmDone);
}

void setup() {
  Serial.begin(115200);
  delay(200);

  ftmDone = xSemaphoreCreateBinary();
  WiFi.onEvent(onFtmReport, ARDUINO_EVENT_WIFI_FTM_REPORT);

  WiFi.mode(WIFI_STA);
  WiFi.begin(FTM_SSID, FTM_PASS);
  Serial.printf("{\"node\":%d,\"status\":\"connecting to %s\"}\n", NODE_ID, FTM_SSID);
  while (WiFi.status() != WL_CONNECTED) {
    delay(250);
  }
  Serial.printf("{\"node\":%d,\"status\":\"connected\"}\n", NODE_ID);
}

void loop() {
  static uint32_t last = 0;
  if (millis() - last < RANGE_MS) return;
  last = millis();

  if (!WiFi.initiateFTM(FTM_FRAME_COUNT, FTM_BURST_PERIOD)) {
    Serial.printf("{\"node\":%d,\"error\":\"ftm_start_failed\"}\n", NODE_ID);
    return;
  }
  if (xSemaphoreTake(ftmDone, pdMS_TO_TICKS(2000)) != pdPASS || !ftmOk) {
    Serial.printf("{\"node\":%d,\"error\":\"ftm_no_report\"}\n", NODE_ID);
    return;
  }
  Serial.printf("{\"node\":%d,\"dist\":%.2f,\"rtt_ns\":%lu,\"t\":%lu}\n",
                NODE_ID, distM, (unsigned long)rttNs, (unsigned long)millis());
}

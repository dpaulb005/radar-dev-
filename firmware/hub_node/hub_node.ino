/*
 * hub_node.ino — aggregation node, stays plugged into the laptop.
 *
 * Listens for ESP-NOW report packets from the rx_node sniffers and
 * prints one JSON object per line over USB serial, which
 * ground_station/locate.py consumes:
 *
 *   {"node":1,"rssi":-54,"n":12,"t":123456}
 *
 * Flash it, open locate.py (not the serial monitor) on its port.
 * At boot it prints its own MAC — copy that into HUB_MAC in rx_node.ino.
 */

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

#define WIFI_CHANNEL 6   // must match drone_beacon / rx_node

typedef struct __attribute__((packed)) {
  uint8_t  node_id;
  int8_t   rssi_median;
  uint8_t  n_samples;
  uint32_t millis_ts;
} report_t;

// arduino-esp32 core v3.x changed the ESP-NOW receive callback signature.
#if ESP_ARDUINO_VERSION >= ESP_ARDUINO_VERSION_VAL(3, 0, 0)
static void onRecv(const esp_now_recv_info_t *info, const uint8_t *data, int len) {
#else
static void onRecv(const uint8_t *mac, const uint8_t *data, int len) {
#endif
  if (len != sizeof(report_t)) return;
  report_t r;
  memcpy(&r, data, sizeof(r));
  Serial.printf("{\"node\":%u,\"rssi\":%d,\"n\":%u,\"t\":%lu}\n",
                r.node_id, r.rssi_median, r.n_samples,
                (unsigned long)r.millis_ts);
}

void setup() {
  Serial.begin(115200);
  delay(200);

  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);

  if (esp_now_init() != ESP_OK) {
    Serial.println("{\"error\":\"esp_now_init failed\"}");
    delay(1000);
    ESP.restart();
  }
  esp_now_register_recv_cb(onRecv);

  Serial.printf("{\"hub_mac\":\"%s\",\"channel\":%d}\n",
                WiFi.macAddress().c_str(), WIFI_CHANNEL);
}

void loop() {
  delay(100);
}

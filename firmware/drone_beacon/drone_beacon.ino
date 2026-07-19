/*
 * drone_beacon.ino — runs on the ESP32 mounted on the drone.
 *
 * Broadcasts a small ESP-NOW beacon at BEACON_HZ so the ground sniffer
 * nodes have a steady stream of frames to measure RSSI on, and (on
 * FTM-capable chips: ESP32-S2/S3/C3/C6) brings up a hidden softAP with
 * the 802.11mc FTM responder enabled so `rx_node_ftm` nodes can do
 * time-of-flight ranging against it.
 *
 * Flash with Arduino IDE + arduino-esp32 core (v2.x or v3.x).
 * On boot it prints its own MAC — copy that into DRONE_MAC in the
 * rx_node firmware.
 *
 * This sketch is standalone. If your drone's main ESP32 runs dedicated
 * flight firmware you can't merge this into (e.g. ESP-FC on the
 * ESP-BLAST), either apply the alive-interval patch described in
 * docs/espblast.md instead, or flash this onto a small piggyback board
 * (ESP32-C3 Super Mini) powered from the drone's 5 V rail.
 */

#include <WiFi.h>
#include <esp_now.h>
#include <esp_wifi.h>

// ---------------- configuration ----------------
#define WIFI_CHANNEL   7        // must match rx_node / hub_node; 7 = espnow-rclink default (see docs/espblast.md)
#define BEACON_HZ      25       // beacon rate; 20-50 is plenty
#define FTM_SSID       "drone-ftm"
#define FTM_PASS       "ftmftmftm"   // >=8 chars; FTM works without association anyway
// -----------------------------------------------

static const uint8_t BCAST[6] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

typedef struct __attribute__((packed)) {
  uint32_t magic;    // 0xDR0NE'ish tag so sniffers can sanity-check
  uint32_t seq;
} beacon_t;

static const uint32_t BEACON_MAGIC = 0xD0BEAC0N;
static beacon_t beacon = {BEACON_MAGIC, 0};
static uint32_t lastBeaconUs = 0;

void setup() {
  Serial.begin(115200);
  delay(200);

  // AP+STA: the softAP provides the FTM responder (where supported),
  // ESP-NOW rides on the same radio/channel.
  WiFi.mode(WIFI_AP_STA);

#if SOC_WIFI_FTM_SUPPORT
  // Last argument enables the FTM responder role on this AP.
  WiFi.softAP(FTM_SSID, FTM_PASS, WIFI_CHANNEL, /*hidden=*/1, /*max_conn=*/4,
              /*ftm_responder=*/true);
  Serial.println("FTM responder: enabled");
#else
  // Original ESP32 chips have no FTM hardware; RSSI mode still works.
  WiFi.softAP(FTM_SSID, FTM_PASS, WIFI_CHANNEL, /*hidden=*/1);
  Serial.println("FTM responder: NOT supported on this chip (RSSI mode only)");
#endif

  esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);

  if (esp_now_init() != ESP_OK) {
    Serial.println("esp_now_init failed, rebooting");
    delay(1000);
    ESP.restart();
  }

  esp_now_peer_info_t peer = {};
  memcpy(peer.peer_addr, BCAST, 6);
  peer.channel = WIFI_CHANNEL;
  peer.ifidx   = WIFI_IF_STA;
  peer.encrypt = false;
  esp_now_add_peer(&peer);

  Serial.print("Drone STA MAC (put this in rx_node DRONE_MAC): ");
  Serial.println(WiFi.macAddress());
  Serial.print("Drone AP  MAC (FTM target): ");
  Serial.println(WiFi.softAPmacAddress());
}

void loop() {
  uint32_t now = micros();
  if (now - lastBeaconUs >= 1000000UL / BEACON_HZ) {
    lastBeaconUs = now;
    beacon.seq++;
    esp_now_send(BCAST, (const uint8_t *)&beacon, sizeof(beacon));
  }
}

# Panduan Lengkap: Smart Parking Slot Detector (Kasus B)
Autonomous System Deployment, UTS Final Project. Deadline: **30 September 2026, 23:00 WIB (ULS)**.

---

## 0. Yang sudah jadi dan status pengujiannya

| Komponen | File | Status |
|---|---|---|
| Edge Agent (Sense-Think-Act-Report, debounce, buffer failover, ukur latensi) | `edge-agent/app.py`, `sensor.py`, `actuator.py` | **Diuji jalan** (Python + Mosquitto asli, 3 slot) |
| Fog: Mosquitto + Aggregator + Dashboard web | `fog/` | **Diuji jalan** (RECV, hitung "tersisa X dari Y", API dashboard) |
| Failover (broker dimatikan 30 detik lalu dinyalakan) | | **Diuji jalan**: LED tetap berganti, 4 pesan di-buffer, terkirim ulang saat pulih |
| Skrip laporan latensi | `scripts/latency_report.py` | **Diuji jalan** |
| Docker (Dockerfile + 3 file compose) | `docker/` | Sintaks divalidasi, **belum saya jalankan** (sandbox saya tidak punya Docker). Kamu yang pertama menjalankan |
| K3s (bonus orkestrasi) | `k8s/` | Sintaks YAML divalidasi, **belum dijalankan** |

Angka latensi dari sandbox saya (max 0,038 ms) hanya gambaran. **Untuk laporan, ukur ulang di laptop dan Raspberry Pi kalian sendiri** (langkah 6).

---

## 1. Arsitektur dan pembagian perangkat

```
RASPBERRY PI (EDGE)                     LAPTOP (FOG + dashboard/"Cloud")
 edge-a1  edge-a2  edge-a3   --MQTT-->   Mosquitto  -->  Aggregator (Flask)
 Sense (sensor simulasi)                 topic parking/lantai-1/slot/+    http://IP-laptop:5000
 Think (< 5 ms, lokal)                   ringkasan: parking/lantai-1/summary
 Act   (LED merah/hijau di terminal)     log: data/telemetry.log
 Report (async, buffer bila putus)
```

Rekomendasi topologi: **Raspberry Pi = Edge, Laptop = Fog**, tersambung lewat hotspot HP.
Alasan: spesifikasi meminta demo failover dengan "cabut WiFi / matikan hotspot". Dengan dua perangkat, itu bisa diperagakan secara nyata, bukan sekadar `docker stop`.

Kalau Raspberry Pi bermasalah, jalankan semuanya di laptop (langkah 4). Spesifikasi mengizinkan, asal dijelaskan jujur.

---

## 2. Setup awal (Ubuntu laptop dan Raspberry Pi OS)

```bash
# Laptop dan RPi
sudo apt update
sudo apt install -y git python3-pip mosquitto-clients
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER      # logout-login sekali setelah ini
docker --version && docker compose version
```

Salin folder project ke laptop (dan ke RPi), misalnya lewat Git:

```bash
cd ~ && git init smart-parking   # atau unzip smart-parking.zip
```

---

## 3. Uji cepat tanpa Docker (5 menit, untuk memastikan kode jalan)

Terminal 1, broker:
```bash
sudo apt install -y mosquitto && sudo systemctl stop mosquitto
mosquitto -v -c fog/mosquitto.conf      # jika error path /mosquitto/data, ganti persistence menjadi false
```
Terminal 2, Fog:
```bash
pip install -r fog/requirements.txt --break-system-packages
cd fog && TELEMETRY_LOG=../data/telemetry.log python3 aggregator.py
```
Terminal 3, Edge (satu slot, fase berganti tiap 8 detik):
```bash
pip install -r edge-agent/requirements.txt --break-system-packages
cd edge-agent && BROKER_HOST=localhost SLOT_ID=A1 SIM_PERIOD=8 LATENCY_FILE=../data/latency-A1.csv python3 app.py
```
Buka `http://localhost:5000`. Kotak A1 berganti hijau/merah, dan terminal Edge menampilkan `ACT -> LED MERAH`.

---

## 4. Jalankan dengan Docker

### Opsi A: semua di satu laptop
```bash
cd docker
docker compose up -d --build
docker compose ps                    # BUKTI DOCKER untuk video (langkah 6 di daftar video)
docker compose logs -f edge-a1       # lihat Sense/Think/Act
```
Dashboard: `http://localhost:5000`.

### Opsi B: Laptop = Fog, RPi = Edge (disarankan)
1. Nyalakan hotspot HP, sambungkan laptop dan RPi ke hotspot yang sama.
2. Di laptop: `hostname -I` (catat IP, contoh `192.168.43.10`).
3. Laptop:
   ```bash
   cd docker && docker compose -f docker-compose.fog.yml up -d --build
   ```
4. RPi (ganti IP sesuai laptop):
   ```bash
   cd docker && echo "FOG_IP=192.168.43.10" > .env
   docker compose -f docker-compose.edge.yml up -d --build
   docker compose -f docker-compose.edge.yml ps
   ```
5. Cek dari laptop: `mosquitto_sub -h localhost -t 'parking/#' -v`

Jika RPi tidak bisa menjangkau broker: cek firewall laptop (`sudo ufw allow 1883/tcp`).

---

## 5. Melihat telemetry MQTT (untuk bukti di video)

```bash
mosquitto_sub -h localhost -t 'parking/#' -v          # semua pesan
mosquitto_sub -h localhost -t 'parking/lantai-1/summary' -v
tail -f data/telemetry.log                             # log yang ditulis Fog
```

| Topic | Isi | QoS | Retain |
|---|---|---|---|
| `parking/lantai-1/slot/A1` | `{"slot_id","status","distance_cm","ts"}` | 1 | ya |
| `parking/lantai-1/agent/A1/online` | `1` (online) / `0` (via Last Will saat putus) | 1 | ya |
| `parking/lantai-1/summary` | `{"free","occupied","total"}` dari Fog | 1 | ya |

Alasan desain (bisa dipakai di dokumentasi):
- **QoS 1**: status slot penting dan jarang berubah, jadi lebih baik dijamin sampai (minimal sekali) daripada QoS 0. QoS 2 dianggap berlebihan karena pesan duplikat tidak berbahaya (status terakhir yang menang).
- **Retain**: dashboard yang baru dibuka langsung mendapat status terakhir tiap slot.
- **Last Will**: broker menandai agent `offline` bila agent mati mendadak.
- **Publish hanya saat status berubah**: hemat bandwidth, sesuai rencana di slide.

---

## 6. Mengukur latensi (bukti angka, bukan klaim)

Agent sudah mengukur otomatis dengan `time.perf_counter_ns()` sebelum dan sesudah fungsi `think()`, lalu menulis ke `data/latency-<slot>.csv`.

Biarkan agent berjalan minimal 5 menit (idealnya 10 menit), lalu:
```bash
python3 scripts/latency_report.py            # dari folder project
```
Output: jumlah sampel, min, rata-rata, p50, p95, p99, maksimum, dan lulus/gagal terhadap 5 ms. **Jalankan ini di RPi** (perangkat Edge yang sesungguhnya) dan tempel hasilnya beserta screenshot di dokumentasi.

Yang harus kamu bisa jelaskan: yang diukur adalah waktu komputasi keputusan (satu perbandingan angka plus debounce), **bukan** waktu baca sensor atau waktu kirim MQTT. Sesuai catatan di slide kelompokmu.

---

## 7. Demo failover (bagian paling berbobot)

Topologi Opsi B. Rekam layar dengan tiga jendela terlihat: (1) log Edge di RPi (SSH dari laptop juga boleh), (2) dashboard Fog, (3) `mosquitto_sub`.

1. Tunjukkan kondisi normal: slot berganti FREE/OCCUPIED, dashboard ikut berubah, `mosquitto_sub` menerima pesan.
2. **Matikan hotspot** (atau `sudo nmcli radio wifi off` di RPi). Ucapkan lantang kapan kamu memutus.
3. Dalam ~5-10 detik log Edge menampilkan `!! MQTT TERPUTUS -> Edge TETAP berjalan`.
4. Tunggu 30-40 detik. Tunjukkan bahwa log tetap mencetak `SENSE ... THINK ... us`, LED tetap berganti (`ACT -> LED MERAH/HIJAU`), dan `REPORT tertunda (offline) -> masuk buffer`. Di sisi Fog tidak ada pesan baru, dashboard membeku, dan agent seharusnya tampil `OFFLINE` lewat Last Will (bagian ini belum sempat saya uji; verifikasi di laptopmu, lihat topic `.../agent/A1/online`).
5. **Nyalakan hotspot kembali.** Log menampilkan `MQTT terhubung` lalu `FAILOVER PULIH: N pesan buffer dikirim ulang`. Dashboard mengejar status terkini.
6. Jelaskan secara teknis: `think()` dan `led.set()` dipanggil sebelum `report()`, dan `report()` tidak pernah melempar exception ke loop utama. Karena itu keputusan tidak bergantung pada respons Fog/Cloud.

Versi cadangan bila hanya satu laptop: `docker stop fog-mosquitto`, tunggu 30 detik, lalu `docker start fog-mosquitto`. Ini sudah saya uji dalam bentuk kill/start proses broker, dengan hasil yang sama.

Batas yang perlu kamu akui jujur di dokumentasi: buffer disimpan di RAM (maks. 500 pesan), jadi bila proses agent mati saat offline, buffer hilang.

---

## 8. Bonus: orkestrasi K3s di Raspberry Pi (Edge Agent sebagai Pod)

Kerjakan **setelah** langkah 1-7 aman.

```bash
# RPi
curl -sfL https://get.k3s.io | sh -
sudo k3s kubectl get nodes

# Bangun image dan impor ke containerd K3s (manifest memakai imagePullPolicy: Never)
cd ~/smart-parking
docker build -f docker/Dockerfile.edge -t parking-agent:1.0 .
docker build -f docker/Dockerfile.fog  -t parking-fog:1.0  .
docker save parking-agent:1.0 | sudo k3s ctr images import -
docker save parking-fog:1.0   | sudo k3s ctr images import -

sudo k3s kubectl apply -f k8s/00-fog.yaml
sudo k3s kubectl apply -f k8s/10-edge-agent.yaml
sudo k3s kubectl get pods -n parking          # BUKTI untuk video
```
Dashboard: `http://IP-RPi:30500`.

Demo singkat untuk video:
- **Self-healing**: `sudo k3s kubectl delete pod -n parking -l slot=A1`, lalu `get pods -w` menunjukkan Pod dibuat ulang otomatis.
- **Scaling (menambah slot)**: `sudo k3s kubectl apply -f k8s/20-edge-a3.yaml`, dan slot A3 muncul di dashboard. Jangan pakai `kubectl scale --replicas=2` pada satu slot: dua agent dengan `client_id` sama akan saling memutus koneksi di broker.

Catatan: pada mode K3s, Mosquitto ikut berjalan di dalam cluster (`00-fog.yaml`), jadi failover jaringan diperagakan dengan `kubectl scale deploy/mosquitto -n parking --replicas=0` lalu `--replicas=1`.

---

## 9. Urutan video demo (6-10 menit) sesuai spesifikasi

| Menit | Isi | Bukti yang harus terlihat |
|---|---|---|
| 0:00-0:40 | Perkenalan, nama kelompok, anggota, kasus | Kartu judul |
| 0:40-2:00 | Diagram Cloud-Fog-Edge, alasan pembagian tier | Diagram di dokumentasi |
| 2:00-3:30 | Demo Sense-Think-Act | Log `SENSE/THINK/ACT`, LED merah/hijau, debounce membuang outlier (400 cm) |
| 3:30-4:30 | Telemetry MQTT | `mosquitto_sub` + dashboard + `telemetry.log` |
| 4:30-7:30 | **Failover** (langkah 7) | Putus jaringan, Edge tetap jalan, buffer, pulih |
| 7:30-8:15 | Bukti Docker | `docker compose ps` / `docker ps` |
| 8:15-9:30 | Bonus K3s | `kubectl get pods`, delete pod, apply A3 |
| 9:30-10:00 | Penutup, kejujuran keterbatasan | Sebut bahwa sensor disimulasikan |

Sebut secara jujur di awal: sensor HC-SR04 dan LED **disimulasikan** karena kelompok tidak memiliki hardware; lapisan `sensor.py` dan `actuator.py` sudah menyediakan versi GPIO (`SENSOR=hw`) yang belum diuji.

---

## 10. Kerangka dokumentasi teknis (PDF)

1. Diagram arsitektur Cloud-Fog-Edge + alasan pembagian (keputusan real-time di Edge, agregasi di Fog, dashboard sebagai tier Cloud sederhana).
2. Pengukuran latensi: metode (`perf_counter_ns` di sekitar `think()`), jumlah sampel, tabel min/rata-rata/p95/p99/max **dari RPi kalian**, screenshot output `latency_report.py`.
3. Skenario failover: apa yang terjadi saat jaringan putus (callback `on_disconnect`, buffer, Act tetap jalan), apa yang terjadi saat pulih (`flush_buffer`), screenshot log.
4. Alur data MQTT: tabel topic, contoh payload, QoS 1 + retain + Last Will dan alasannya (bagian 5).
5. Trade-off (pilih minimal satu, sebaiknya dua):
   - Debounce 2 pembacaan: status stabil tetapi telat ~1 detik dibanding pembacaan mentah.
   - Buffer di RAM: sederhana dan cepat, tetapi hilang bila proses mati.
   - Publish hanya saat berubah + retain: hemat bandwidth, tetapi Fog tidak bisa membedakan "tidak ada perubahan" dari "agent macet" tanpa Last Will.
   - Sensor simulasi: bisa diuji berulang, tetapi tidak menangkap noise fisik sebenarnya.
6. Tabel kontribusi anggota (Jevon Valentino, Valens Oliver, Nicholas Davian, Rafael Briliant, Yudhistira Satria): isi bagian dan persentase yang **benar**.
7. **Lampirkan screenshot/link chat AI ini** (wajib menurut spesifikasi).

---

## 11. Struktur repo dan checklist pengumpulan

```
smart-parking/
  edge-agent/   app.py sensor.py actuator.py requirements.txt
  fog/          aggregator.py mosquitto.conf requirements.txt
  cloud/        (dashboard sudah ada di fog/aggregator.py; tulis catatan di README)
  docker/       Dockerfile.* docker-compose*.yml
  k8s/          manifest K3s
  scripts/      latency_report.py
  data/         (hasil latensi & log; boleh disertakan sebagai bukti)
```
Checklist:
- [ ] Video MP4 6-10 menit (YouTube unlisted / Drive akses terbuka), failover terlihat jelas
- [ ] Repo Git (dosen di-invite) atau zip terstruktur
- [ ] PDF dokumentasi lengkap (angka latensi nyata, tabel kontribusi, chat AI)
- [ ] Semua dikumpulkan lewat ULS sebelum 30 September 23:00 WIB

Saran jadwal: **28 Sep** setup dan uji (langkah 2-6), **29 Sep** failover, K3s, rekam video, **30 Sep pagi** dokumentasi PDF, kirim sebelum sore.

---

## 12. Yang harus kamu pahami sebelum demo (penilaian individu)

Spesifikasi menilai kejujuran dan pemahaman. Pastikan tiap anggota bisa menjawab:
- Mengapa `set_led()` dipanggil **sebelum** `publish()`? (agar aksi tidak bergantung pada jaringan)
- Apa fungsi `CONFIRM_N` dan mengapa outlier `> 200 cm` dibuang?
- Apa beda `on_disconnect` dan buffer, dan kapan pesan buffer dikirim ulang?
- Mengapa QoS 1, bukan 0 atau 2?
- Mengapa latensi 5 ms hanya berlaku untuk `think()`?

---

## 13. Masalah umum

| Gejala | Solusi |
|---|---|
| Edge terus `TERPUTUS`/`terhubung` bergantian | Ada dua agent dengan `SLOT_ID` sama. Hentikan yang lama (`docker compose down`, `ps aux | grep app.py`) |
| RPi tidak bisa ke broker | Cek IP laptop di `.env`, `sudo ufw allow 1883/tcp`, dan pastikan satu jaringan |
| `permission denied` Docker | `sudo usermod -aG docker $USER`, lalu logout-login |
| Dashboard kosong | Tunggu satu siklus (SIM_PERIOD), cek `docker compose logs fog-aggregator` |
| `data/` tidak terisi di Docker | Pastikan menjalankan compose dari folder `docker/` (volume relatif `../data`) |

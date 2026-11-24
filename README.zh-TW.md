# PawPrint Light Controller

[English](README.md) · [MIT 授權](LICENSE)

這是 Home Assistant 的自訂整合。它讓 DG-LAB 爪印 V1.1 透過低功耗藍牙控制一盞燈，由 Home Assistant 接收感測資料並呼叫燈光服務。整合可以在區域網路內運作，不需要另外架伺服器、MQTT Broker 或建立 Home Assistant Token。

| 操作 | 燈光動作 |
| --- | --- |
| 短按 | 燈亮時依序切換白、紅、橙、綠、青、藍、紫。燈關著時用上次選擇的顏色開燈，第一次為白色。 |
| 按住不動，再放開 | 關燈。 |
| 按住並傾斜 | 調整亮度。調到 0% 時關燈，回到 0% 以上時重新亮起，放開即結束調光。 |

## 需要的設備

- 第一代 **爪印 V1.1**，藍牙廣播名稱為 `47L120300`。如果看到 `47L120100`，請依原廠說明更新韌體。 [DG-LAB 爪印藍牙協定](https://github.com/dungeonlab-open/dglab-bluetooth-protocol/blob/main/paw-prints/README.md#bluetooth-name)
- 已啟用 Bluetooth 整合的 Home Assistant，以及範圍內可建立 BLE 連線的藍牙介面。用 Home Assistant Container 搭配主機藍牙時，依官方說明掛載主機的 D-Bus 並設定介面權限。 [Home Assistant Bluetooth 文件](https://www.home-assistant.io/integrations/bluetooth/)
- Home Assistant 裡的 `light.*` 實體。燈具需支援色彩及亮度才能使用全部手勢。

已用爪印 V1.1 實機、樹莓派內建藍牙、Home Assistant Container 2026.10.1 和 Matter 彩色燈具驗證。

## 安裝和配對

1. 下載或 clone 此專案，把 `custom_components/pawprint_light/` 複製到 Home Assistant 設定目錄內的 `custom_components/`。如果沒有這個目錄，先建立它。安裝後，Home Assistant 裡的檔案路徑會像是 `/config/custom_components/pawprint_light/manifest.json`。
2. 將 [sample.yaml](sample.yaml) 的 `pawprint_light:` 和日誌設定加到 `configuration.yaml`，把 `light.example_lamp` 換成你的燈具實體 ID。若已有 `logger:`，把元件的日誌等級加到原有的 `logs:` 底下。範例以 `dry_run: true` 開始，可以先看手勢事件。
3. 檢查設定並重啟 Home Assistant。關掉原本連著爪印的 App 或網頁，開啟爪印後長按到肩燈白藍交替閃爍。掃描範圍內只有一顆符合條件的爪印時，整合會自動連線。
4. 在「設定 → 系統 → 日誌」確認出現 `Pawprint connected and reporting sensor data`，接著放開按鈕。在「開發者工具 → 事件」監聽 `pawprint_light_gesture` 再試按。事件包含 `gesture`（`color`、`off` 或 `brightness`）和 `brightness_pct`（調光時為 0–100，其他手勢為 `null`）。
5. 把日誌中的藍牙位址填入 `address`，讓整合在重啟後也連到同一顆爪印。設成 `dry_run: false` 啟用控燈。校準完成後可設成 `debug: false`，再把元件日誌等級調為 `info`。檢查設定並重啟即可生效。

## 校準調光

將 `debug` 與元件日誌等級分別設為 `true` 和 `debug`。左右傾斜爪印時觀察日誌中的 `XYZ`，選變化最明顯的軸填入 `axis`。將 0% 姿勢的讀數填入 `left`，將 100% 姿勢的讀數填入 `right`。兩個數字互換即可反轉方向。這些值是感測器的原始讀數。若平放旋轉變化不明顯，可改用左右傾斜。

| 欄位 | 預設值 | 用途 |
| --- | --- | --- |
| `light` | 必填 | 要控制的燈具實體 |
| `address` | 自動探索 | 爪印的藍牙位址。範圍內有多顆時請指定 |
| `axis` | `x` | 用於調光的感測軸，可用 `x`、`y` 或 `z` |
| `left`、`right` | `-60`、`60` | 0% 與 100% 的原始讀數，範圍為 −128 到 127，兩值須相異 |
| `hold_seconds` | `0.5` | 長按門檻，單位為秒 |
| `motion_threshold` | `12` | 移動門檻，使用原始讀數 |
| `speed_threshold` | `35` | 移動速度門檻，使用每秒原始讀數變化量 |
| `debug` | `false` | 以 debug 等級記錄原始感測資料 |
| `dry_run` | `false` | 發送手勢事件，略過燈光服務呼叫 |

爪印約每 100 毫秒回報一次，極快的點按可能被漏掉。若資料中斷，未完成的手勢會被丟棄，整合會嘗試重連。如果爪印停止廣播，請喚醒它或重新進入配對模式。調光會將姿勢對應到絕對亮度，開始調光時可能跳到目前姿勢對應的亮度。

## 開發與測試

手勢測試可用 Python 3.9 以上執行。

```sh
python3 -m unittest -v test_gesture
```

完整測試用 Home Assistant Core 執行，會以模擬的藍牙通知驗證初始化、手勢事件和燈光服務呼叫。執行方式見[英文 README 的開發章節](README.md#development)。

專案程式採 [MIT 授權](LICENSE)。藍牙實作參考 [DG-LAB 爪印 V1.1 協定](https://github.com/dungeonlab-open/dglab-bluetooth-protocol/blob/main/paw-prints/README.md)。

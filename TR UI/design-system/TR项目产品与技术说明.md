# TR Report System — 產品與技術說明

本文檔梳理 **TR UI** 專案的產品功能、使用角色，以及後端 **Flask API**（`backend/tr_fill_in_api.py`）與各功能的對應關係與業務邏輯要點。部署形態為：**Nginx 提供靜態頁面並將 `/api` 反代至後端**，資料庫支援 **SQLite / PostgreSQL**（由 `db_adapter` 等模組適配）。

---

## 一、產品定位與架構概覽

### 1.1 產品定位

面向內部或授權用戶的 **TR（Test Report）記錄管理與報告工具**：

- 查詢、篩選訂單與交貨/項目資訊（TR 主數據、`bbs_dd` 輔表）。
- 生成、下載 **TR PDF**（異步任務），維護生成狀態（`PDF_Status`）。
- 下載 **Stockist & Test Report** 等附件（依文件索引、異步打包 ZIP）。
- 管理員：**全量數據更新**（階段 A 同步 + 階段 B 批處理）、帳號與文件索引維護。

### 1.2 技術架構（簡圖）

```
瀏覽器 → Nginx（靜態 HTML/CSS/JS） 
              → location /api/ → Flask（tr_fill_in_api.py，預設 :5000）
              → 業務 DB（SQLite 或 PostgreSQL）
              → 本地目錄（Generated_PDFs、Stockist&Test Report 等）
```

### 1.3 前端主要頁面

| 頁面 | 說明 |
|------|------|
| `login.html` | 登入，取得 Token 後寫入 `sessionStorage` |
| `tr-records.html` | 主工作台：TR 記錄列表、搜索、PDF 生成/下載、STOCKIST & TEST 分頁、管理員「更新數據」 |
| `user-management.html` | 管理員帳號 CRUD（Nginx 可對外網限制，僅內網訪問 `user-management.html`） |
| `dashboard.html` / `index.html` / `super-admin.html` | 其他入口或演示/舊版界面（主業務以 `tr-records` 為核心） |

前端 API 基址由 `config.js` 決定：經 Nginx 同源訪問時通常為 **`/api`**（與後端路徑一致）。

### 1.4 身份與授權

- **認證**：登入後返回 `token`；後續請求在 Header（如 `Authorization` / 自定義頭，以 `require_auth` 實現為準）帶入會話。
- **角色**：至少包含 `admin`、`manager`、`user`。
  - **`user`**：訂單列表僅能看帳號綁定的 **Job No** 範圍；下載 PDF 等同理按 Job 隔離。
  - **`manager` / `admin`**：可看全部訂單（列表與下載邏輯中不按 Job 過濾）。
- **限流**：登入、管理操作、PDF 生成、下載、系統類 POST 等設有 **flask-limiter** 配額（可用環境變數覆蓋，見 `env.rate_limit.example`）。

---

## 二、功能模塊與 API 對照總表

### 2.1 認證與個人資料

| 功能 | 方法與路徑 | 認證 | 邏輯摘要 |
|------|------------|------|----------|
| 登入 | `POST /api/auth/login` | 否 | 校驗帳密（鹽+慢哈希）、查活躍狀態、寫入 `user_sessions`、返回 `token` 與用戶基本信息（含 `job_nos`）；登入限流 |
| 登出 | `POST /api/auth/logout` | 是 | 刪除當前 token 對應會話 |
| 當前用戶 | `GET /api/auth/me` | 是 | 讀庫刷新 `job_nos` 等；結果可緩存（約 30 分鐘） |

### 2.2 管理員 — 帳號管理

| 功能 | 方法與路徑 | 認證 | 邏輯摘要 |
|------|------------|------|----------|
| 用戶列表 | `GET /api/admin/users` | admin | 讀 `user_accounts` + 各用戶 `job_nos`；列表可緩存（約 5 分鐘） |
| 新建用戶 | `POST /api/admin/users` | admin | 創建 `user`/`manager`，密碼過期策略寫入；`user` 可寫入 Job 綁定；清理列表緩存 |
| 更新用戶 | `PUT /api/admin/users/<username>` | admin | 更新姓名、啟用狀態、密碼（重算過期）、`user` 的 `job_nos`；禁止禁用/改壞預留 `admin` |
| 刪除用戶 | `DELETE /api/admin/users/<username>` | admin | 刪除帳號及關聯；禁止刪 `admin`、禁止自刪 |
| 重置密碼 | `POST /api/admin/users/<username>/reset-password` | admin | 管理員重置密碼（含限流） |

### 2.3 TR 訂單列表與分組（主列表）

| 功能 | 方法與路徑 | 認證 | 邏輯摘要 |
|------|------------|------|----------|
| 訂單列表 | `GET /api/orders/list` | 可選* | Query：`page`、`per_page`、`tab`、`order_no`、`job_no`、`dn_no`、`start_date`、`end_date`。`tab=records`：主表 `TR_Report_Deduplication`，左連 `PDF_Status`（若表存在）帶 `pdf_status/path/generated_at`；`tab=stocklist-test`：走 `bbs_dd` 專用列表。`user` 角色自動附加 **Job No IN (...)** 條件。結果可緩存（約 5 分鐘）。 |
| 按 Job 分組統計 | `GET /api/orders/group-by-job-no` | 可選* | 在 `TR_Report_Deduplication` 上按 `Job_No` 聚合（筆數、重量、日期範圍、客戶串）；`user` 同樣 Job 過濾。 |

\* 路由層未強制 `require_auth` 時，後端以 `get_current_user(optional=True)` 區分匿名與登入；**生產環境建議由網關或代碼層保證僅授權可訪問**。

### 2.4 TR 填寫數據（Tag / `TR_Fill_in`）與材料查詢

用於從 `materials_com` 選料寫入 `TR_Fill_in`，並聯動再生 **`Orders_gen_pdf`** 匯總表。

| 功能 | 方法與路徑 | 認證 | 邏輯摘要 |
|------|------------|------|----------|
| 讀取 TR_Fill_in | `GET /api/tr-fill-in/data` | 否* | `SELECT * FROM TR_Fill_in` |
| 保存 Tag | `POST /api/tr-fill-in/save` | 否* | Body：`tag_nos[]` → 從 `materials_com` 查行 → `INSERT OR IGNORE` 到 `TR_Fill_in`；若有新增則調用 **`regenerate_orders_gen_pdf()`** 同步 `Orders_gen_pdf` |
| 刪除 Tag | `POST /api/tr-fill-in/delete` | 否* | 按 Tag 刪除；若有刪除則再生 `Orders_gen_pdf` 並清理訂單列表緩存 |
| 清空 | `POST /api/tr-fill-in/clear` | 否* | 清空 `TR_Fill_in` 並再生 `Orders_gen_pdf`、清緩存 |
| 更新單筆 | `POST /api/tr-fill-in/update` | 否* | 白名單字段更新 `TR_Fill_in`；成功則再生 `Orders_gen_pdf`、清緩存 |
| 手動再生匯總表 | `POST /api/orders-gen-pdf/regenerate` | 否（系統限流） | 僅觸發 `regenerate_orders_gen_pdf()` |
| 查單筆匯總 | `GET /api/orders-gen-pdf/<order_no>` | 否* | 讀 `Orders_gen_pdf` 表頭 + 明細行 |
| 編輯匯總 | `POST /api/orders-gen-pdf/<order_no>/edit` | 否* | Body：`header_updates`、`line_updates`（按 rowid）更新 `Orders_gen_pdf`；若有變更可觸發後續與 PDF 狀態相關邏輯（見代碼尾部） |
| 按 Tag 查材料 | `GET /api/materials/search/<tag_no>` | 否* | 查 `materials_com`；可緩存；表不存在時返回調試性表名列表（DEBUG 下） |

\* 這組接口在當前代碼中多未加 `require_auth`，**對外公網部署時強烈建議加認證或僅內網開放**。

### 2.5 TR PDF 生成與下載

| 功能 | 方法與路徑 | 認證 | 邏輯摘要 |
|------|------------|------|----------|
| 創建生成任務 | `POST /api/pdf/generate` | 是 | Body：`order_no`；`PDFTaskManager` 入庫任務、後台異步生成；限流 |
| 任務狀態 | `GET /api/pdf/task-status/<task_id>` | 是 | 按 `user_id` 隔離查詢；狀態含 `pending/processing/completed/failed`、進度、完成時路徑與告警標記 |
| 下載單個 PDF | `GET /api/pdf/download/<order_no>` | 是 | 讀 `PDF_Status` + `TR_Report_Deduplication`；`user` 校验 **Job_No**；路徑須在 `backend/Generated_PDFs` 下（防目錄穿越）；缺文件時可按 `Del_Date` 嘗試補掃並回寫狀態 |
| 批量 ZIP | `POST /api/pdf/batch-download` | 是 | Body：`order_nos`（上限 200 等）；校驗權限後打 ZIP 下載 |

### 2.6 Stockist & Test Report（文件索引 + 異步下載）

依賴環境變量 **`STOCKIST_TEST_FOLDER`**（默認某盤目錄）及資料庫中的 **`file_index_cache`** 等表。

| 功能 | 方法與路徑 | 認證 | 邏輯摘要 |
|------|------------|------|----------|
| 索引狀態 | `GET /api/file-index/status` | 是 | 統計索引條數、元數據、掃描狀態；索引大小目前實現對 SQLite 使用 `pragma_page_count`（**PostgreSQL 環境下該段可能需要適配**） |
| 全量重建索引 | `POST /api/file-index/rebuild` | admin | 後台線程跑 `FileIndexBuilder.build_index` |
| 增量更新索引 | `POST /api/file-index/update` | admin | `FileIndexUpdater.update_index`；可能快速返回統計或「後台執行中」 |
| 清理幽靈記錄 | `POST /api/file-index/cleanup` | admin | 掃描庫中路徑，磁盤不存在則標記 `is_deleted`（注意 **SQL 佔位符在 PostgreSQL 下可能需 ? → %s 適配**，以實際 `db_adapter` 為準） |
| 單筆 Order 下載任務 | `GET /api/stockist-test/download-by-order/<order_no>` | 是 | `DownloadTaskManager` 創建並入隊 `order` 任務 |
| 按 DD_No 下載 | `GET /api/stockist-test/download-by-dd-no/<dd_no>` | 是 | 走 `StockistTestDownloader`：關聯 `bbs_dd` 等多張表彙總文件（詳見 `stockist_test_download.py`） |
| 多 Order 同步打包（舊/直連式） | `POST /api/stockist-test/download-by-order-nos` 等 | 是 | 多數已改為 **異步 task_id**；大量訂單有上限（如 500） |
| 按日期/分組等批量 | `POST /api/stockist-test/download-by-order-nos-grouped-by-dd-no`、`...by-date`、`get-date-count` | 是 | 參數體與分組規則見路由 docstring；用於 STOCKIST 頁批量操作 |
| 扁平 Stockist 目錄打包 | `POST /api/stockist-test/download-all-stockist-nos` | 是 | 任務類型 `order_stockist_flat`，ZIP 內按 Stockist_No 目錄扁平存放 |
| 通用異步創建任務 | `POST /api/download/create-task` | 是 | Body：`type` = `order` / `dd_no` / `date` + `params.order_nos` |
| 任務狀態 | `GET /api/download/task-status/<task_id>` | 是 | 進度、`zip_path`、完成後 `download_url` |
| 下載 ZIP | `GET /api/download/download/<task_id>` | 是 | 流式返回 ZIP，傳輸後延遲刪除臨時文件 |

### 2.7 系統 — 全量數據更新（管理員）

| 功能 | 方法與路徑 | 認證 | 邏輯摘要 |
|------|------------|------|----------|
| 啟動全量更新 | `POST /api/system/update-all-tables` | admin | 檢查批處理文件存在；**單例**：若內存/磁盤狀態為 `sync` 或 `batch` 則 409；否則 `run_id`、寫 `full_update_job_state.json`、啟動後台線程 **`_full_update_worker`**：階段 A（如 `sync_tr_data` 日誌）→ 階段 B（計劃任務或直接 `auto_update_all_tables.bat`） |
| 查詢進度 | `GET /api/system/check-update-status` | admin | 合併內存與 JSON 狀態；必要時依日誌 `try_reconcile_full_update_from_logs` 修正為 `completed/failed` |

### 2.8 運維與健康檢查

| 功能 | 方法與路徑 | 認證 | 邏輯摘要 |
|------|------------|------|----------|
| 健康檢查 | `GET /health` | 否 | 輸出 `health_check` 模組聚合狀態（不可用時降級為簡單 JSON） |

---

## 三、數據庫表與說明

### 3.1 參考來源與初始化方式

| 來源 | 說明 |
|------|------|
| **`backend/schema_postgres.sql`** | PostgreSQL 下一批**核心業務表 + 應用表**的權威 DDL（可作新建庫參考）。 |
| **`tr_fill_in_api.py` 啟動時** | `_ensure_account_tables`、`_ensure_file_index_tables`、`_ensure_download_tasks_table`、`_ensure_pdf_tasks_table` 會在連上資料庫時 **CREATE IF NOT EXISTS** 賬號、索引、`PDF_Status`、任務表等（SQLite / PG 分支略有差異）。 |
| **批處理 / 同步腳本** | `TR_Report`、`TR_Report_Deduplication`、`bbs_dd`、`materials_com`、`orders_com` 等主要由 **全量更新流水線**或獨立 Python 腳本從上游系統灌入，不一定由 API 建表。 |

實際欄位類型在 **SQLite（TEXT/DATE 寬鬆）** 與 **PostgreSQL（類型更嚴、帶時區）** 之間會有差異，排查問題時请以當前庫 `information_schema` / `\d` / `pragma table_info` 為準。

---

### 3.2 表分組一覽

| 分組 | 表名 | 主要用途 |
|------|------|----------|
| 帳號與授權 | `user_accounts`、`user_job_access`、`user_sessions` | 登入、角色、Job 範圍、會話 token |
| 業務主數據（ETL） | `TR_Report`、`TR_Report_Deduplication`、`bbs_dd` | 訂單/項目列表、去重列表、DD 維度輔表 |
| PDF 產物 | `PDF_Status` | 每張訂單 TR PDF 的生成狀態與相對路徑 |
| 異步任務 | `pdf_tasks`、`download_tasks` | PDF 生成任務、Stockist&Test 打包下載任務 |
| 檔案索引 | `file_index_cache`、`file_index_metadata` | 掃描本地目錄後的檔案索引與掃描元數據 |
| 填報流水線 | `materials_com`、`TR_Fill_in`、`orders_com`、`Orders_gen_pdf` | 選料 → 填表 → 與訂單維度關聯 → 生成列印用寬表 |

---

### 3.3 帳號、Job 範圍與會話

#### `user_accounts`

| 欄位（邏輯名） | 說明 |
|----------------|------|
| `id` | 主鍵 |
| `username` | 登入名，唯一 |
| `password_hash` / `password_salt` | 慢哈希+鹽，不存明文 |
| `full_name` | 顯示名 |
| `role` | `admin` / `manager` / `user`（庫內 CHECK 約束） |
| `is_active` | 是否可用 |
| `created_at` / `updated_at` | 審計時間 |
| `password_changed_at` / `password_expires_at` | 密碼輪轉與過期（`user`/`manager` 常用） |

#### `user_job_access`

| 欄位 | 說明 |
|------|------|
| `user_id` | 關聯 `user_accounts.id`，級聯刪除 |
| `job_no` | 授權給該 **user** 的 Job 編號（一對多）；**manager/admin** 列表邏輯不依賴此表 |

唯一約束：`(user_id, job_no)`，避免重複綁定。

#### `user_sessions`

| 欄位 | 說明 |
|------|------|
| `token` | 即 API 返回的會話令牌（主鍵） |
| `user_id` | 所屬用戶 |
| `created_at` / `expires_at` | 生命週期；過期後 `_get_session` 會刪除 |

登入時會清除該用戶舊會話（單端/單會話策略，以代碼為準）。

---

### 3.4 業務主數據表（列表與報表數據源）

#### `TR_Report`

- **含義**：從上游（如 SQL Server）同步的 **明細級** TR 數據，一行可對應直徑/證書粒度。
- **主要欄位**：`order_no`、`Job_No`、`del_date`、`client`、`各類證書與產品字段`、`rm_dn_no`、`jobsite_type` 等（見 `schema_postgres.sql`）。
- **使用**：統計、同步、生成去重表的來源之一；**前端主列表默認用去重表**而非直接讀本表。

#### `TR_Report_Deduplication`

- **含義**：按 **`Order_No` 唯一** 去重後的「訂單頭」表，供 **`/api/orders/list?tab=records`**、權限過濾、與 `PDF_Status` 關聯。
- **主要欄位**：`Order_No`、`Job_No`、`Client`、`Jobsite`、`Order_Description`、`Del_Date`、`PO_No`、`Jobsite_Type`、`Wt`、`Grade`、`rm_dn_no` 等。
- **索引**：按 `Job_No`、`Del_Date`、`rm_dn_no`、`Jobsite_Type` 等查詢優化（見 DDL）。

#### `bbs_dd`

- **含義**：與 STOCKIST & TEST 業務相關的 **BBS/DD 維度**（`bbs_no`、站點、DD 編號、交貨日、訂單描述、`jobsite_type`）。
- **使用**：**`/api/orders/list?tab=stocklist-test`** 走 `bbs_dd` 的列表分支；下載 API 中與 `dd_no`、日期分組等邏輯關聯。

---

### 3.5 PDF 狀態與異步任務表

#### `PDF_Status`（PostgreSQL 中表名帶雙引號大小寫）

| 欄位 | 說明 |
|------|------|
| `Order_No` | 主鍵，對應去重表訂單號 |
| `pdf_status` | 如 `pending` / `generated` / `failed`（實際取值以業務寫入為準） |
| `pdf_path` | 相對 `backend` 的生成路徑或磁盤相對路徑 |
| `generated_at` / `updated_at` | 生成時間與更新時間 |

下載接口會結合 `TR_Report_Deduplication` 做 **Job_No 權限**校驗，並校驗文件落在允許目錄下。

#### `pdf_tasks`

| 欄位 | 說明 |
|------|------|
| `task_id` | UUID 字符串主鍵 |
| `user_id` / `order_no` | 任務歸屬與目標訂單 |
| `status` | `pending` / `processing` / `completed` / `failed` |
| `progress`、`message`、`pdf_path`、`error_message` | 進度與結果 |
| 時間欄位 | `created_at`、`started_at`、`completed_at`、`expires_at` |

對應 **`POST /api/pdf/generate`** 與 **`GET /api/pdf/task-status/...`**。

#### `download_tasks`

| 欄位 | 說明 |
|------|------|
| `task_id` | 主鍵 |
| `user_id` | 歸屬用戶 |
| `task_type` | 如 `order`、`dd_no`、`date`、`order_stockist_flat` 等（與 `DownloadTaskManager` 一致） |
| `request_params` | PG 為 **JSONB**；SQLite 多為 JSON 文本 |
| `status`、`progress`、`total_files`、`processed_files` | 打包進度 |
| `zip_path`、`zip_size` | 完成後臨時 ZIP |
| `error_message`、`warning_message` | 失敗原因或部分文件缺失告警 |
| 時間欄位 | 同上 |

對應 **Stockist&Test 異步下載**與 **`/api/download/*`**。

---

### 3.6 文件索引（Stockist & Test 目錄掃描）

#### `file_index_cache`

- **含義**：掃描 **`STOCKIST_TEST_FOLDER`** 下約定子目錄後，每個文件一行索引。
- **重要欄位**：`file_path`（唯一）、`file_name`、`folder_path`、`folder_type`（枚舉：`Stockist Cert`、`Private Formal`、`Private Prelim`、`IAT Formal`、`IAT Prelim`）、`file_size`、`modified_time`、`extracted_keywords`、`identifiers`、`file_hash`、`is_deleted`。
- **用途**：按關鍵字/標識符快速定位 PDF，供下載器組裝 ZIP。

#### `file_index_metadata`

- **含義**：索引任務的**鍵值配置**（小表）。
- **常見 key**：`last_full_scan`、`total_files_indexed`、`index_version`、`scan_status`（`idle` / `scanning` / `updating` 等）。

更口語化的對照說明可見 **`backend/TABLE_EXPLANATION.md`**（侧重這兩張索引表）。

---

### 3.7 填報流水線相關表（非 `schema_postgres.sql` 全量覆蓋）

以下表通常由 **同步腳本**或歷史 SQLite 庫繼承而來；API 依賴其存在與否（例如 `regenerate_orders_gen_pdf` 會檢測表存在性）。

#### `materials_com`

- **含義**：材料主數據，至少含 **`Tag_No`** 及與證書、規格相關列。
- **使用**：**`GET /api/materials/search/<tag_no>`**；**`POST /api/tr-fill-in/save`** 按 `Tag_No` 批次查入後寫入 `TR_Fill_in`。

#### `TR_Fill_in`

- **含義**：用戶為生成報告而**勾選/維護**的材料行（工運工作台的中間層）。
- **典型欄位**（與 `save`/`insert` 邏輯一致）：`Dia`、`Len`、`Product`、`Pattern`、`Tag_No`、`Mill_Cert`、`Test_Cert1`、`Test_Cert2`、`Stockist_Cert`、`PO_No`、`DN_No`、`Grade`（可為空，匯總時從訂單補）、以及常見的 `id` / `updated_at`（若表結構由遷移腳本擴展）。
- **API**：`/api/tr-fill-in/*` 全套。

#### `orders_com`

- **含義**：訂單級別的匯總維度（至少含 `Dia`、`Order_No`、`Job_No`、`Client`、`Del_Date`、`Grade`、`Wt` 等），與 `TR_Fill_in` **按 `Dia` 關聯**。
- **使用**：**`regenerate_orders_gen_pdf()`** 中 `INNER JOIN orders_com oc ON tf.Dia = oc.Dia`。若此表不存在，匯總表不會生成。

#### `Orders_gen_pdf`

- **含義**：**寬表**，將 `TR_Fill_in` 與 `orders_com` 拼成「表頭 + 多行明細」平面結構，供 **`GET/POST /api/orders-gen-pdf/...`** 與 PDF 模板數據源使用。
- **生成方式**：`DROP` 後 **`CREATE TABLE Orders_gen_pdf AS SELECT ...`**（見 `_full_update` 以外的 `regenerate_orders_gen_pdf`）；**非增量**，以整表替換為主。
- **邏輯列名示例**：`'Wt(ton)'`、`'PO_No(1)'`、`'PO_No(2)'` 等（帶括號的列名在 SQL 中需注意引號）。

---

### 3.8 表之間的業務關係（簡圖）

```
user_accounts ──< user_job_access     （user 的 Job 範圍）
       │
       └──< user_sessions              （登入 token）

TR_Report  ──(ETL)──>  TR_Report_Deduplication  ──<  PDF_Status
                                              │
                                              └──  PDF 文件（磁盤 `Generated_PDFs`）

bbs_dd  ──(列表 tab=stocklist-test、下載維度)──>  前端 / stockist_test_download

materials_com  ──(Tag_No)──>  TR_Fill_in  ──(Dia)──>  orders_com
                              │
                              └── regenerate ──>  Orders_gen_pdf  ──>  PDF 生成 / 編輯 API

file_index_cache  ──(路徑/關鍵字)──>  download_tasks / 下載 workers
```

---

## 四、與前端的典型調用鏈（示例）

### 4.1 登入 → 拉列表

1. `POST /api/auth/login` → 存 `token`  
2. `GET /api/auth/me` → 側欄顯示角色與是否顯示管理入口  
3. `GET /api/orders/list?tab=records&...` → 渲染表格與 PDF 狀態列  

### 4.2 生成 PDF

1. `POST /api/pdf/generate` `{ order_no }` → `task_id`  
2. 輪詢 `GET /api/pdf/task-status/<task_id>`  
3. 完成後 `GET /api/pdf/download/<order_no>` 或頁面內嵌下載鏈接  

### 4.3 管理員更新全庫

1. `POST /api/system/update-all-tables`  
2. 輪詢 `GET /api/system/check-update-status` 直至 `completed` / `failed`  

---

## 五、維護與擴展注意點

1. **安全**：部分 `tr-fill-in`、`orders-gen-pdf`、`materials` 路由未強制登入時，外網部署應補 **認證或 IP 限制**。  
2. **PostgreSQL**：列表與 PDF 路徑邏輯已做引號表名等適配；**文件索引狀態/清理** 等處若仍含 `?` 佔位或 SQLite PRAGMA，需在 PG 環境逐項驗證。  
3. **緩存**：訂單列表、材料搜索、用戶列表等使用內存緩存；管理或批量更新後會有部分 `cache.delete`；故障排查時可關注是否「看到舊數據」。  
4. **環境變數**：資料庫路徑、`CORS_ORIGINS`、`STOCKIST_TEST_FOLDER`、全量更新任務名、限流與 `API_HOST`（建議反代時僅監聽 `127.0.0.1`）等。  

---

## 六、文檔修订说明

- 路由與邏輯以 **`backend/tr_fill_in_api.py`** 当前实现为准；若后续增减 `@app.route`，请以代码为准更新本表。
- **數據庫表結構**以 **`backend/schema_postgres.sql`** 及應用啟動時 DDL 為主；**`file_index_cache` / `file_index_metadata`** 的補充說明見 **`backend/TABLE_EXPLANATION.md`**。
- 细节实现（如 `StockistTestDownloader` 内文件匹配规则、PDF 渲染模板）见对应 `*.py` / `backend/templates/`。

---

*文档生成说明：基于仓库内 `tr_fill_in_api.py` 路由扫描与核心段落阅读整理。*

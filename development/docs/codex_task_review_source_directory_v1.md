# Codex 任务：review-module 资料包 source_directory 功能

任务版本：V1
编写时间：2026-03-28
优先级：P1
涉及文件：`review-module/server.py`、`review-module/app.js`、`review-module/index.html`

---

## 背景

当前资料包文件列表从 task JSON 的 `document_package.files` 直接读取。
对于系统自动生成的 review task，files 已由拆解流程填充，显示正常。

**缺口**：用户想对新产品（不在 10款重疾 目录内）发起人工审核时，无法为 task 指定文件包目录。

**目标**：在 task JSON 中增加 `document_package.source_directory` 字段，允许用户通过页面指定目录，服务端动态扫描目录中的文件并返回。

---

## 验收标准

1. 未设置 `source_directory` 时，资料包行为与现在完全一致（显示 task JSON 内的 files）
2. 设置 `source_directory` 后，刷新页面，资料包显示该目录下扫描到的 PDF/XLSX 文件
3. 可以修改 `source_directory`，修改后立即生效
4. `source_directory` 路径不存在时，PATCH 接口返回 400 错误，task JSON 不更新
5. 全程不修改 `~/code/aix-engine/` 任何文件

---

## 一、server.py 修改

### 1.1 新增 `scan_directory_files(directory_path)` 函数

放在类定义之前（工具函数区域）。

```python
FILENAME_SOURCE_TYPE_MAP = [
    ("条款", "clause"),
    ("费率表", "raw_rate"),
    ("说明书", "brochure"),
    ("核保", "underwriting"),
]

def scan_directory_files(directory_path: str) -> list:
    """扫描目录，返回 document_package files 列表。"""
    dir_path = Path(directory_path).expanduser()
    if not dir_path.is_dir():
        return []
    files = []
    for f in sorted(dir_path.iterdir()):
        if f.suffix.lower() not in {".pdf", ".xlsx", ".xls"}:
            continue
        source_type = "other"
        for keyword, stype in FILENAME_SOURCE_TYPE_MAP:
            if keyword in f.name:
                source_type = stype
                break
        files.append({
            "source_type": source_type,
            "file_name": f.name,
            "parse_quality": "available",
            "local_path": str(f),
        })
    return files
```

### 1.2 修改 `do_GET` 中的 `/tasks/{product_id}` 处理

在读取 task JSON 后、写入响应前，插入 source_directory 解析逻辑：

```python
# 原有逻辑：
if parsed.path.startswith("/tasks/"):
    product_id = parsed.path[len("/tasks/"):].strip("/")
    task_file = TASKS_DIR / f"{product_id}_review_task_v2.json"
    if not task_file.exists():
        self.send_error(404, f"Task not found: {product_id}")
        return
    data = task_file.read_bytes()
    # === 新增：source_directory 动态解析 ===
    try:
        task_data = json.loads(data)
        src_dir = task_data.get("document_package", {}).get("source_directory")
        if src_dir:
            scanned = scan_directory_files(src_dir)
            if scanned:
                task_data["document_package"]["files"] = scanned
                data = json.dumps(task_data, ensure_ascii=False).encode("utf-8")
    except Exception:
        pass  # 解析失败时原样返回
    # === 结束新增 ===
    self.send_response(200)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Access-Control-Allow-Origin", "*")
    self.end_headers()
    self.wfile.write(data)
    return
```

### 1.3 新增 `do_PATCH` 方法

在 `do_GET` 之后、`do_POST` 之前（或类的任意位置）添加：

```python
def do_PATCH(self):
    parsed = urlparse(self.path)
    if not parsed.path.startswith("/tasks/"):
        self.send_error(404, "Not Found")
        return

    product_id = parsed.path[len("/tasks/"):].strip("/")
    task_file = TASKS_DIR / f"{product_id}_review_task_v2.json"
    if not task_file.exists():
        self.send_error(404, f"Task not found: {product_id}")
        return

    content_length = int(self.headers.get("Content-Length", "0"))
    raw = self.rfile.read(content_length) if content_length > 0 else b"{}"
    try:
        payload = json.loads(raw.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        self.send_error(400, "Invalid JSON")
        return

    src_dir = payload.get("document_package", {}).get("source_directory")
    if src_dir is None:
        self.send_error(400, "Missing document_package.source_directory")
        return

    # 验证目录存在
    dir_path = Path(src_dir).expanduser()
    if not dir_path.is_dir():
        self._json_error(400, f"Directory not found: {src_dir}")
        return

    # 更新 task JSON
    task_data = json.loads(task_file.read_text(encoding="utf-8"))
    if "document_package" not in task_data:
        task_data["document_package"] = {}
    task_data["document_package"]["source_directory"] = str(dir_path)
    task_file.write_text(json.dumps(task_data, ensure_ascii=False, indent=2), encoding="utf-8")

    self.send_response(200)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Access-Control-Allow-Origin", "*")
    self.end_headers()
    self.wfile.write(json.dumps({"ok": True, "source_directory": str(dir_path)}, ensure_ascii=False).encode("utf-8"))

def _json_error(self, code: int, message: str):
    body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
    self.send_response(code)
    self.send_header("Content-Type", "application/json; charset=utf-8")
    self.send_header("Content-Length", str(len(body)))
    self.end_headers()
    self.wfile.write(body)
```

### 1.4 新增 OPTIONS 预检支持（CORS）

```python
def do_OPTIONS(self):
    self.send_response(204)
    self.send_header("Access-Control-Allow-Origin", "*")
    self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, OPTIONS")
    self.send_header("Access-Control-Allow-Headers", "Content-Type")
    self.end_headers()
```

---

## 二、app.js 修改

### 2.1 新增 PATCH 调用函数

在 `loadTask()` 函数附近（文件头部工具函数区），新增：

```javascript
async function setSourceDirectory(productId, dirPath) {
  const res = await fetch(`/tasks/${productId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_package: { source_directory: dirPath } }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.error || `HTTP ${res.status}`);
  }
  return res.json();
}
```

### 2.2 修改 `renderTopbar()` 中的资料包区域

在现有 `packageFiles.querySelectorAll("[data-open-path]")...` 的 forEach 结束后（约 line 429），追加 source_directory UI 渲染：

```javascript
// === 新增：source_directory 区域 ===
const srcDir = state.task?.document_package?.source_directory || "";
const srcDirNode = document.createElement("div");
srcDirNode.className = "source-dir-row";
if (srcDir) {
  srcDirNode.innerHTML = `
    <div class="source-dir-label">文件包目录</div>
    <div class="source-dir-path" title="${srcDir}">${srcDir}</div>
    <button type="button" class="btn-secondary source-dir-btn" id="btnChangeDir">修改</button>
  `;
} else {
  srcDirNode.innerHTML = `
    <div class="source-dir-label source-dir-unset">未指定文件包目录</div>
    <button type="button" class="btn-secondary source-dir-btn" id="btnSetDir">指定目录</button>
  `;
}
packageFiles.appendChild(srcDirNode);

// 输入框（初始隐藏）
const inputRow = document.createElement("div");
inputRow.className = "source-dir-input-row";
inputRow.style.display = "none";
inputRow.innerHTML = `
  <input type="text" id="sourceDirInput" class="source-dir-input" placeholder="粘贴目录绝对路径，例如 /Users/xxx/Desktop/产品文件夹" value="${srcDir}" />
  <button type="button" class="btn-primary" id="btnConfirmDir">确认</button>
  <button type="button" class="btn-secondary" id="btnCancelDir">取消</button>
  <span id="sourceDirStatus" class="source-dir-status"></span>
`;
packageFiles.appendChild(inputRow);

// 事件绑定
const btnSet = packageFiles.querySelector("#btnSetDir, #btnChangeDir");
if (btnSet) {
  btnSet.addEventListener("click", () => {
    inputRow.style.display = "flex";
    btnSet.style.display = "none";
  });
}
packageFiles.querySelector("#btnConfirmDir")?.addEventListener("click", async () => {
  const val = packageFiles.querySelector("#sourceDirInput").value.trim();
  if (!val) return;
  const statusEl = packageFiles.querySelector("#sourceDirStatus");
  statusEl.textContent = "保存中…";
  try {
    await setSourceDirectory(state.task.product.product_id, val);
    statusEl.textContent = "已保存，正在刷新…";
    // 重新加载 task 以更新文件列表
    state.task = await loadTask();
    state.task.document_package = state.task.document_package || { files: [] };
    renderTopbar();
  } catch (e) {
    statusEl.textContent = `错误：${e.message}`;
  }
});
packageFiles.querySelector("#btnCancelDir")?.addEventListener("click", () => {
  inputRow.style.display = "none";
  const btnSet2 = packageFiles.querySelector("#btnSetDir, #btnChangeDir");
  if (btnSet2) btnSet2.style.display = "";
  packageFiles.querySelector("#sourceDirStatus").textContent = "";
});
// === 结束新增 ===
```

---

## 三、index.html / styles.css 修改

### 3.1 styles.css 新增样式

在 `.package-files` 相关样式区域后追加：

```css
.source-dir-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  flex-wrap: wrap;
}
.source-dir-label {
  font-size: 12px;
  color: var(--text-secondary);
  white-space: nowrap;
}
.source-dir-unset {
  font-style: italic;
}
.source-dir-path {
  font-size: 12px;
  color: var(--text-primary);
  word-break: break-all;
  flex: 1;
}
.source-dir-input-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  flex-wrap: wrap;
}
.source-dir-input {
  flex: 1;
  min-width: 240px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 4px;
  font-size: 12px;
}
.source-dir-status {
  font-size: 12px;
  color: var(--text-secondary);
}
.source-dir-btn {
  font-size: 12px;
  padding: 2px 10px;
}
```

---

## 四、不做的事

- 不做原生文件夹选择器（浏览器安全限制，用粘贴路径代替）
- 不改现有文件上传、删除逻辑
- 不改 task JSON 中的其余字段
- 不修改 `~/code/aix-engine/` 任何文件

---

## 五、快速验收步骤

```
1. 重启 server.py
2. 打开任意产品的 review 页面
3. 确认资料包区域底部出现"未指定文件包目录"+ "指定目录"按钮
4. 点击"指定目录"，粘贴一个有 PDF 文件的目录（如 ~/Desktop/开发材料/10款重疾/889-...）
5. 点击"确认"→ 刷新后文件列表更新为该目录下的文件
6. 对一个不存在的路径点击确认 → 页面显示错误提示，文件列表不变
```

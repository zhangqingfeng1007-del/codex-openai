// DATA_SOURCE: "mock" | "local" | "api"
//   mock  — loads ./mock/review-task-v2.json (static fixture)
//   local — loads /tasks/{PRODUCT_ID} from server.py (real generated task)
//   api   — loads from API_BASE (production backend)
const DATA_SOURCE = "local";
const PRODUCT_ID = "1010003851";
const API_BASE = "http://localhost:3001/api/v1";
const TASK_ID = "task_20260326_001";
const MOCK_DATA_URL = "./mock/review-task-v2.json";
const STANDARD_HINTS_BLOCKLIST = new Set([
  "合同名称（条款名称）",
  "条款编码",
  "报备年度",
  "生效时间"
]);
const ACTION_LABELS = [
  { action: "accepted", zh: "接受", en: "Accept" },
  { action: "modified", zh: "修改", en: "Modify" },
  { action: "rejected", zh: "拒绝", en: "Reject" },
  { action: "not_applicable", zh: "不适用", en: "Skip / N/A" }
];
const SOURCE_TYPE_LABELS = {
  clause: "条款 clause",
  product_brochure: "说明书 product_brochure",
  processed_rate: "费率表 processed_rate",
  raw_rate: "原始费率 raw_rate",
  underwriting_rule: "核保规则 underwriting_rule",
  manual: "人工录入 manual"
};

const state = {
  task: null,
  standardValues: {},
  decisions: {},
  selectedItemId: null,
  collapsedGroups: new Set(),
  searchTerm: "",
  submitState: "idle"
};

const productTitle = document.getElementById("productTitle");
const companyName = document.getElementById("companyName");
const taskStatusText = document.getElementById("taskStatusText");
const ruleVersion = document.getElementById("ruleVersion");
const progressText = document.getElementById("progressText");
const riskSummary = document.getElementById("riskSummary");
const progressFill = document.getElementById("progressFill");
const fieldGroupList = document.getElementById("fieldGroupList");
const searchInput = document.getElementById("searchInput");
const packageId = document.getElementById("packageId");
const packageFiles = document.getElementById("packageFiles");
const topbarMain = document.querySelector(".topbar-main");
const evidenceTitle = document.getElementById("evidenceTitle");
const dependencyBanner = document.getElementById("dependencyBanner");
const sourcesList = document.getElementById("sourcesList");
const logicTrace = document.getElementById("logicTrace");
const decisionWarning = document.getElementById("decisionWarning");
const decisionCoverageName = document.getElementById("decisionCoverageName");
const decisionBadges = document.getElementById("decisionBadges");
const candidateSummary = document.getElementById("candidateSummary");
const finalValueInput = document.getElementById("finalValueInput");
const sourceFileSelect = document.getElementById("sourceFileSelect");
const sourcePageInput = document.getElementById("sourcePageInput");
const sourceQuoteInput = document.getElementById("sourceQuoteInput");
const actionRow = document.getElementById("actionRow");
const reasonCode = document.getElementById("reasonCode");
const reviewComment = document.getElementById("reviewComment");
const saveDecision = document.getElementById("saveDecision");
const submitImport = document.getElementById("submitImport");
const submitStatus = document.getElementById("submitStatus");
const standardValueHints = document.getElementById("standardValueHints");

const STATUS_LABELS = {
  pending_review: { zh: "待认领", en: "pending_review", color: "#6b7280", bg: "#f3f4f6" },
  in_review: { zh: "复核中", en: "in_review", color: "#2563eb", bg: "#dbeafe" },
  review_completed: { zh: "复核完成", en: "review_completed", color: "#16a34a", bg: "#dcfce7" },
  returned_for_materials: { zh: "打回补资料", en: "returned_for_materials", color: "#0891b2", bg: "#cffafe" },
  import_submitted: { zh: "入库已提交", en: "import_submitted", color: "#16a34a", bg: "#dcfce7" },
  import_failed: { zh: "入库失败", en: "import_failed", color: "#dc2626", bg: "#fee2e2" },
  archived: { zh: "已归档", en: "archived", color: "#6b7280", bg: "#f3f4f6" },
  candidate_ready: { zh: "候选就绪", en: "candidate_ready", color: "#16a34a", bg: "#dcfce7" },
  review_required: { zh: "需复核", en: "review_required", color: "#d97706", bg: "#fef3c7" },
  accepted: { zh: "已接受", en: "accepted", color: "#2563eb", bg: "#dbeafe" },
  modified: { zh: "已修改", en: "modified", color: "#7c3aed", bg: "#ede9fe" },
  rejected: { zh: "已拒绝", en: "rejected", color: "#dc2626", bg: "#fee2e2" },
  cannot_extract: { zh: "无法提取", en: "cannot_extract", color: "#6b7280", bg: "#f3f4f6" },
  cannot_extract_from_clause: { zh: "条款无法提取", en: "cannot_extract_from_clause", color: "#6b7280", bg: "#f3f4f6" },
  pending_materials: { zh: "待补材料", en: "pending_materials", color: "#0891b2", bg: "#cffafe" },
  not_extracted: { zh: "未抽取", en: "not_extracted", color: "#8b5cf6", bg: "#ede9fe" },
  manually_added: { zh: "已补录", en: "manually_added", color: "#d97706", bg: "#fef3c7" },
  not_applicable: { zh: "不适用", en: "not_applicable", color: "#9ca3af", bg: "#f9fafb" }
};

function statusClass(status) {
  return `badge badge-${status || "review_required"}`;
}

function statusLabel(status) {
  return STATUS_LABELS[status]?.zh || status;
}

function applyStatusStyle(element, status) {
  const meta = STATUS_LABELS[status];
  if (meta?.color && meta?.bg) {
    element.style.color = meta.color;
    element.style.background = meta.bg;
  } else {
    element.style.color = "";
    element.style.background = "";
  }
}

function renderStatusBadge(status) {
  const s = STATUS_LABELS[status] || { zh: status, en: status, color: "#6b7280", bg: "#f3f4f6" };
  return `<span class="status-badge" style="color:${s.color};background:${s.bg};">${s.zh}<span class="status-en">${s.en}</span></span>`;
}

function isTerminalStatus(status) {
  return ["accepted", "modified", "cannot_extract", "cannot_extract_from_clause", "not_applicable"].includes(status);
}

function isBlockingStatus(status) {
  return ["review_required", "candidate_ready", "not_extracted", "pending_materials", "rejected"].includes(status);
}

async function loadTask() {
  if (DATA_SOURCE === "api") {
    const response = await fetch(`${API_BASE}/review/tasks/${TASK_ID}`);
    if (!response.ok) {
      throw new Error(`任务加载失败：${response.status}`);
    }
    const body = await response.json();
    return body.data ?? body;
  }
  if (DATA_SOURCE === "local") {
    const response = await fetch(`/tasks/${PRODUCT_ID}`);
    if (!response.ok) {
      throw new Error(`本地任务加载失败：${response.status}（product_id=${PRODUCT_ID}）`);
    }
    return response.json();
  }
  const response = await fetch(MOCK_DATA_URL);
  if (!response.ok) {
    throw new Error(`Mock 数据加载失败：${response.status}`);
  }
  return response.json();
}

async function loadStandardValues() {
  try {
    const res = await fetch("/standard_values");
    if (!res.ok) return {};
    return res.json();
  } catch {
    return {};
  }
}

async function loadProductList() {
  try {
    const res = await fetch("/tasks");
    if (!res.ok) return [];
    const body = await res.json();
    return body.product_ids || [];
  } catch {
    return [];
  }
}

async function submitReview(payload) {
  if (DATA_SOURCE !== "api") {
    console.log("[mock] review submit", payload);
    return { ok: true };
  }
  const response = await fetch(`${API_BASE}/review/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
  if (!response.ok) {
    throw new Error(`提交失败：${response.status}`);
  }
  return response.json();
}

function getAllItems() {
  return (state.task?.field_groups || [])
    .filter((group) => !group.is_dynamic)
    .flatMap((group) => group.items || []);
}

function findItemById(itemId) {
  return getAllItems().find((item) => item.item_id === itemId);
}

function getDecision(itemId) {
  return state.decisions[itemId] || null;
}

function getEffectiveStatus(item) {
  return getDecision(item.item_id)?.status || item.status;
}

function getEffectiveFinalValue(item) {
  const decision = getDecision(item.item_id);
  if (decision?.final_value !== undefined) return decision.final_value;
  const firstSource = item.sources?.[0];
  return item.final_value || firstSource?.normalized_value || "";
}

function getEffectiveSourceMeta(item) {
  const decision = getDecision(item.item_id);
  if (decision?.source_file || decision?.source_page || decision?.source_quote) {
    return {
      source_file: decision?.source_file || "",
      source_page: decision?.source_page || "",
      source_quote: decision?.source_quote || ""
    };
  }
  const firstSource = item.sources?.[0];
  return {
    source_file: firstSource?.file_name || "",
    source_page: firstSource?.page ?? "",
    source_quote: firstSource?.source_raw_value || firstSource?.md_text || ""
  };
}

function findLocalPathByFileName(fileName) {
  if (!fileName) return null;
  const files = state.task?.document_package?.files || [];
  const match = files.find((f) => f.file_name === fileName);
  return match?.local_path || null;
}

function getClauseDocumentFile() {
  return ((state.task?.document_package?.files) || []).find((file) => file.source_type === "clause") || null;
}

function buildManualSource(item, status, finalValue) {
  if (status === "not_applicable") {
    return {
      source_id: `manual_${item.item_id}_na`,
      source_type: "manual",
      file_name: null,
      page: null,
      block_id: null,
      title_path: [],
      source_raw_value: "复核员确认：本产品不涉及此字段，标记为不适用。",
      md_text: "",
      block_text: "复核员确认：本产品不涉及此字段，标记为不适用。",
      raw_value: finalValue || "",
      normalized_value: finalValue || "",
      confidence: 1,
      extract_method: "manual_review:not_applicable",
      confirmation_type: "not_applicable",
      conflict: false
    };
  }
  if (status === "accepted" && finalValue === "不支持") {
    const clauseFile = getClauseDocumentFile();
    return {
      source_id: `manual_${item.item_id}_negative_absence`,
      source_type: "manual",
      file_name: clauseFile?.file_name || null,
      page: null,
      block_id: null,
      title_path: [],
      source_raw_value: "经人工通读条款，未见相关权益约定。",
      md_text: "",
      block_text: "经人工通读条款，未见相关权益约定。",
      raw_value: finalValue,
      normalized_value: finalValue,
      confidence: 1,
      extract_method: "manual_review:negative_absence",
      confirmation_type: "negative_absence",
      conflict: false
    };
  }
  return null;
}

function renderStandardHints(item) {
  if (!standardValueHints) return;
  if (!item) {
    standardValueHints.innerHTML = "";
    return;
  }
  if (STANDARD_HINTS_BLOCKLIST.has(item.coverage_name)) {
    standardValueHints.innerHTML = "";
    return;
  }

  const allValues = state.standardValues[item.coverage_name] || [];
  if (!allValues.length) {
    standardValueHints.innerHTML = "";
    return;
  }

  const keyword = finalValueInput.value.trim();
  const filtered = keyword
    ? allValues.filter((v) => v.includes(keyword))
    : allValues;

  if (!filtered.length) {
    standardValueHints.innerHTML = "";
    return;
  }

  standardValueHints.innerHTML = `
    <div class="standard-hints-label">已知标准值参考 known standard values（${filtered.length}/${allValues.length}）</div>
    <div class="standard-hints-chips">${filtered.map((v) =>
      `<button type="button" class="hint-chip" data-value="${v.replace(/"/g, "&quot;")}">${v}</button>`
    ).join("")}</div>
  `;
}

function getItemSummary(item) {
  const decision = getDecision(item.item_id);
  if (decision?.final_value) return decision.final_value;
  return item.candidate_summary || "—";
}

function countReviewedItems() {
  return getAllItems().filter((item) => {
    const status = getEffectiveStatus(item);
    return !isBlockingStatus(status) && isTerminalStatus(status);
  }).length;
}

function findDependencyGroup(coverageName) {
  return state.task.dependency_groups.find((group) => group.members.includes(coverageName)) || null;
}

function getLinkedMembers(item) {
  const group = findDependencyGroup(item.coverage_name);
  return group ? new Set(group.members) : new Set();
}

function detectDependencyConflict() {
  const payTimesItem = getAllItems().find((item) => item.coverage_name === "重疾赔付次数");
  const groupingItem = getAllItems().find((item) => item.coverage_name === "重疾分组");
  if (!payTimesItem || !groupingItem) return null;
  const payTimes = getEffectiveFinalValue(payTimesItem);
  const grouping = getEffectiveFinalValue(groupingItem);
  if (payTimes === "1次" && grouping && grouping !== "不涉及") {
    return "依赖冲突：重疾赔付次数=1次，但重疾分组不是“不涉及”。";
  }
  return null;
}

function createEmptyState(text) {
  const div = document.createElement("div");
  div.className = "empty-state";
  div.textContent = text;
  return div;
}

async function copyText(value) {
  if (!value) return;
  try {
    await navigator.clipboard.writeText(value);
    submitStatus.textContent = "路径已复制";
  } catch {
    submitStatus.textContent = "复制失败";
  }
}

async function openLocalPath(path) {
  if (!path) return;
  try {
    const response = await fetch("/__open", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path })
    });
    if (!response.ok) {
      throw new Error(`打开失败：${response.status}`);
    }
    submitStatus.textContent = "已调用本机打开";
  } catch (error) {
    submitStatus.textContent = error.message;
  }
}

function renderTopbar() {
  const { task = {}, product = {}, document_package = { files: [] } } = state.task || {};
  productTitle.textContent = product.product_name;
  const total = state.task.total_items || getAllItems().length;
  companyName.textContent = `product_id: ${product.product_id} · 共 ${total} 项 total`;
  taskStatusText.textContent = `${product.company_name} · ${statusLabel(task.task_status)} ${STATUS_LABELS[task.task_status]?.en || task.task_status}`;
  ruleVersion.textContent = `规则版本 ${task.rule_version}`;
  packageId.textContent = document_package.document_package_id;

  const reviewed = countReviewedItems();
  const percentage = total ? (reviewed / total) * 100 : 0;
  progressText.textContent = `${reviewed} / ${total} 已裁决`;
  const conflict = state.task.conflict_count || 0;
  const missing = state.task.missing_count || 0;
  const notExtracted = state.task.not_extracted_count || 0;
  const pending = state.task.pending_review_count || 0;
  riskSummary.textContent = `冲突 ${conflict} conflict  ·  缺失 ${missing} missing  ·  未抽取 ${notExtracted} not_extracted  ·  待处理 ${pending} pending`;
  progressFill.style.width = `${percentage}%`;

  packageFiles.innerHTML = "";
  (document_package.files || []).forEach((file) => {
    const node = document.createElement("div");
    node.className = "file-chip";
    node.innerHTML = `
      <div class="file-chip-main">
        <div>
          <div>${SOURCE_TYPE_LABELS[file.source_type] || file.source_type} · ${file.file_name}</div>
          <div class="file-path">${file.local_path || "未定位本机存储路径"}</div>
        </div>
        <div class="file-chip-actions">
          <span>${file.parse_quality}</span>
          ${file.local_path ? `<button type="button" class="file-open-link" data-open-path="${file.local_path}">打开</button>` : `<span class="file-open-link is-disabled">未定位</span>`}
          ${file.local_path ? `<button type="button" class="file-copy-btn" data-path="${file.local_path}">复制路径</button>` : ""}
        </div>
      </div>
    `;
    packageFiles.appendChild(node);
  });

  packageFiles.querySelectorAll(".file-copy-btn").forEach((button) => {
    button.addEventListener("click", () => copyText(button.dataset.path));
  });
  packageFiles.querySelectorAll("[data-open-path]").forEach((button) => {
    button.addEventListener("click", () => openLocalPath(button.dataset.openPath));
  });

  submitImport.disabled = reviewed !== total || total === 0 || state.submitState === "submitting";
}

async function renderProductSelector() {
  const productIds = await loadProductList();
  if (!productIds.length) return;

  let selector = document.getElementById("productSelector");
  if (!selector) {
    const wrap = document.createElement("div");
    wrap.className = "topbar-subline";
    wrap.innerHTML = `
      <span>切换产品 product</span>
      <select id="productSelector" class="text-input" style="max-width:220px;padding:6px 10px;font-size:12px;"></select>
    `;
    topbarMain?.appendChild(wrap);
    selector = wrap.querySelector("#productSelector");
  }
  selector.innerHTML = productIds.map((id) =>
    `<option value="${id}" ${id === state.task?.product?.product_id ? "selected" : ""}>${id}</option>`
  ).join("");

  if (!selector.dataset.bound) {
    selector.addEventListener("change", async (e) => {
      const newId = e.target.value;
      if (!newId || newId === state.task?.product?.product_id) return;
      state.decisions = {};
      state.selectedItemId = null;
      state.searchTerm = "";
      state.collapsedGroups = new Set();
      state.submitState = "idle";
      submitStatus.textContent = "";
      try {
        const res = await fetch(`/tasks/${newId}`);
        if (!res.ok) throw new Error(`加载失败：${res.status}`);
        state.task = await res.json();
        state.task.field_groups = state.task.field_groups || [];
        state.task.dependency_groups = state.task.dependency_groups || [];
        state.task.document_package = state.task.document_package || { files: [] };
        const firstItem = getAllItems()[0];
        state.selectedItemId = firstItem?.item_id || null;
        renderAll();
        await renderProductSelector();
      } catch (err) {
        alert(`产品切换失败：${err.message}`);
      }
    });
    selector.dataset.bound = "true";
  }
}

function renderFieldGroups() {
  const activeItem = findItemById(state.selectedItemId);
  const linkedMembers = activeItem ? getLinkedMembers(activeItem) : new Set();
  const searchTerm = state.searchTerm.trim();

  fieldGroupList.innerHTML = "";

  const groups = [...(state.task?.field_groups || [])].sort((a, b) => {
    if (a.is_dynamic && !b.is_dynamic) return -1;
    if (!a.is_dynamic && b.is_dynamic) return 1;
    return 0;
  });

  groups.forEach((group) => {
    const items = group.is_dynamic
      ? (group.item_ids || []).map((id) => findItemById(id)).filter(Boolean)
      : (group.items || []);

    const visibleItems = items.filter((item) => {
      if (!searchTerm) return true;
      return item.coverage_name.includes(searchTerm) || getItemSummary(item).includes(searchTerm);
    });
    if (!visibleItems.length) return;

    const wrapper = document.createElement("section");
    wrapper.className = `group-block ${state.collapsedGroups.has(group.group_type) ? "is-collapsed" : ""}`;

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "group-toggle";
    const dynamicIcon = group.is_dynamic
      ? (group.group_type === "dynamic_not_extracted" ? "🟣 " : "⬜ ")
      : "";
    toggle.innerHTML = `
      <div class="group-title-row">
        <span class="group-title">${dynamicIcon}${group.group_name}</span>
        <span class="group-summary">${visibleItems.length} 项</span>
      </div>
    `;
    toggle.addEventListener("click", () => {
      if (state.collapsedGroups.has(group.group_type)) {
        state.collapsedGroups.delete(group.group_type);
      } else {
        state.collapsedGroups.add(group.group_type);
      }
      renderFieldGroups();
    });
    wrapper.appendChild(toggle);

    const itemsWrap = document.createElement("div");
    itemsWrap.className = "group-items";

    visibleItems.forEach((item) => {
      const status = getEffectiveStatus(item);
      const sourcesCount = item.source_count ?? item.sources.length;
      const itemSources = item.sources || [];
      const hasConflict = itemSources.some((source) => source.conflict) || sourcesCount > 1;

      const row = document.createElement("button");
      row.type = "button";
      row.className = `field-item ${item.item_id === state.selectedItemId ? "is-active" : ""} ${linkedMembers.has(item.coverage_name) ? "is-linked" : ""}`;
      if (status === "not_extracted") {
        row.style.opacity = "0.68";
      }
      row.addEventListener("click", () => {
        state.selectedItemId = item.item_id;
        renderAll();
      });

      row.innerHTML = `
        <div class="field-item-head">
          <span class="conflict-mark">${hasConflict ? "🔴" : "•"}</span>
          <div>
            <div class="field-name">${item.coverage_name}</div>
            <div class="item-meta">${sourcesCount} 个来源</div>
          </div>
          ${renderStatusBadge(status)}
        </div>
        <div class="field-item-body">
          <div class="item-summary">${status === "not_extracted" ? "模板存在，未被抽取" : getItemSummary(item)}</div>
          <div class="source-meta">${hasConflict ? "冲突" : "正常"}</div>
        </div>
      `;
      itemsWrap.appendChild(row);
    });

    wrapper.appendChild(itemsWrap);
    fieldGroupList.appendChild(wrapper);
  });
}

function renderSources() {
  const item = findItemById(state.selectedItemId);
  evidenceTitle.textContent = item ? `${item.coverage_name} · 全部来源` : "选择左侧字段查看来源。";
  const dependencyGroup = item ? findDependencyGroup(item.coverage_name) : null;
  const dependencyConflict = detectDependencyConflict();

  if (dependencyGroup) {
    dependencyBanner.className = "decision-warning is-visible";
    dependencyBanner.textContent = `依赖组：${dependencyGroup.group_name} · 成员：${dependencyGroup.members.join("、")}`;
  } else {
    dependencyBanner.className = "decision-warning";
    dependencyBanner.textContent = "";
  }

  sourcesList.innerHTML = "";
  if (!item) {
    sourcesList.appendChild(createEmptyState("请选择左侧字段。"));
    return;
  }
  const itemSources = item?.sources || [];
  const decision = getDecision(item.item_id);
  if (!itemSources.length && !decision?.manual_source) {
    sourcesList.appendChild(createEmptyState(item.status === "not_extracted" ? "模板存在，但抽取层未产出来源候选。" : "当前字段暂无来源候选。"));
    return;
  }

  itemSources.forEach((source) => {
    const confidencePercent = Math.round((source.confidence || 0) * 100);
    const confClass = confidencePercent >= 90 ? "high" : confidencePercent >= 70 ? "mid" : "low";
    const localPath = findLocalPathByFileName(source.file_name);
    const openBtn = localPath
      ? `<button type="button" class="file-open-link" data-open-path="${localPath}" title="打开来源文件">打开</button>`
      : `<span class="file-open-link is-disabled">未定位</span>`;
    const card = document.createElement("article");
    card.className = `source-card ${source.conflict ? "is-conflict" : ""}`;
    card.innerHTML = `
      <div class="source-head">
        <div>
          <div class="source-type">${SOURCE_TYPE_LABELS[source.source_type] || source.source_type}</div>
          <div class="source-file">${source.file_name}</div>
          <div class="source-meta">第 ${source.page ?? "-"} 页 · ${source.block_id ?? "无 block"} · ${(source.title_path || []).join(" > ") || "无标题路径"}</div>
        </div>
        <div style="display:flex;align-items:center;gap:6px;">
          ${renderStatusBadge(source.conflict ? "rejected" : "accepted")}
          ${openBtn}
        </div>
      </div>
      <div class="source-values">
        <div class="value-block">
          <label>原文来源值</label>
          <div class="value-box">${source.source_raw_value || "—"}</div>
        </div>
        <div class="value-block">
          <label>候选标准值</label>
          <div class="value-box">${source.normalized_value || source.raw_value || "—"}</div>
        </div>
      </div>
      <div class="source-text">${source.md_text || source.block_text || "无文本"}</div>
      <div class="confidence-row">
        <span class="value-meta">${source.extract_method}</span>
        <div class="confidence-bar ${confClass}"><span style="width:${confidencePercent}%"></span></div>
        <span class="value-meta">${confidencePercent}%</span>
      </div>
    `;
    sourcesList.appendChild(card);
  });

  if (decision?.manual_source) {
    const ms = decision.manual_source;
    const card = document.createElement("article");
    card.className = "source-card manual-source-card";
    const confirmTypeLabel = ms.confirmation_type === "negative_absence"
      ? "负向确认 negative_absence"
      : "不适用确认 not_applicable";
    card.innerHTML = `
      <div class="source-head">
        <div>
          <div class="source-type">人工录入 manual</div>
          <div class="source-file">${ms.file_name || "—"}</div>
          <div class="source-meta">页码：— · ${confirmTypeLabel}</div>
        </div>
      </div>
      <div class="source-values">
        <div class="value-block">
          <label>来源说明</label>
          <div class="value-box">${ms.block_text}</div>
        </div>
      </div>
    `;
    sourcesList.appendChild(card);
  }

  if (dependencyConflict) {
    const alert = document.createElement("div");
    alert.className = "decision-warning is-visible";
    alert.textContent = dependencyConflict;
    sourcesList.prepend(alert);
  }
}

function renderLogicTrace() {
  const item = findItemById(state.selectedItemId);
  logicTrace.innerHTML = "";
  if (!item) {
    logicTrace.appendChild(createEmptyState("请选择左侧字段查看判定链路。"));
    return;
  }

  const sections = [
    ["来源优先级", item.logic_trace?.priority_trace || []],
    ["规范化过程", item.logic_trace?.normalization_trace || []],
    ["最终映射", item.logic_trace?.mapping_trace || []]
  ];

  sections.forEach(([title, rows]) => {
    const node = document.createElement("section");
    node.className = "trace-node";
    node.innerHTML = `<h4>${title}</h4>`;
    if (!rows.length) {
      node.appendChild(createEmptyState("无记录"));
    } else {
      const list = document.createElement("ul");
      rows.forEach((row) => {
        const li = document.createElement("li");
        li.textContent = row;
        list.appendChild(li);
      });
      node.appendChild(list);
    }
    logicTrace.appendChild(node);
  });
}

function renderDecisionPanel() {
  const item = findItemById(state.selectedItemId);
  decisionBadges.innerHTML = "";
  decisionWarning.className = "decision-warning";
  decisionWarning.textContent = "";

  if (!item) {
    decisionCoverageName.textContent = "请选择字段";
    candidateSummary.textContent = "—";
    finalValueInput.value = "";
    sourceFileSelect.innerHTML = `<option value="">请选择来源文件</option>`;
    sourcePageInput.value = "";
    sourceQuoteInput.value = "";
    reasonCode.value = "";
    reviewComment.value = "";
    updateActionButtons(null);
    return;
  }

  const decision = getDecision(item.item_id);
  const status = getEffectiveStatus(item);
  const dependencyConflict = detectDependencyConflict();
  const dependencyGroup = findDependencyGroup(item.coverage_name);
  const sourceMeta = getEffectiveSourceMeta(item);

  decisionCoverageName.innerHTML = `
    <div class="item-header">
      <span class="item-name-zh">${item.coverage_name}</span>
      <span class="item-meta">coverage_id: ${item.coverage_id} · ${item.group_level_1} <span class="meta-en">${item.group_type}</span> · ${item.catalog_version}</span>
    </div>
  `;
  candidateSummary.textContent = item.candidate_summary || "—";
  finalValueInput.value = getEffectiveFinalValue(item);
  renderStandardHints(item);

  sourceFileSelect.innerHTML = `<option value="">请选择来源文件</option>`;
  ((state.task?.document_package?.files) || []).forEach((file) => {
    const option = document.createElement("option");
    option.value = file.file_name;
    option.textContent = `${file.source_type} · ${file.file_name}`;
    sourceFileSelect.appendChild(option);
  });
  sourceFileSelect.value = sourceMeta.source_file || "";
  sourcePageInput.value = sourceMeta.source_page || "";
  sourceQuoteInput.value = sourceMeta.source_quote || "";
  reasonCode.value = decision?.reason_code || "";
  reviewComment.value = decision?.review_comment || "";

  const statusBadge = document.createElement("span");
  statusBadge.innerHTML = renderStatusBadge(status);
  decisionBadges.appendChild(statusBadge);

  if (status === "manually_added" && item.manually_added_by) {
    const manualBadge = document.createElement("span");
    manualBadge.className = "badge badge-pending_review";
    manualBadge.textContent = `补录人 ${item.manually_added_by}`;
    decisionBadges.appendChild(manualBadge);
  }

  if (dependencyGroup) {
    const groupBadge = document.createElement("span");
    groupBadge.className = "badge badge-in_review";
    groupBadge.textContent = dependencyGroup.group_name;
    decisionBadges.appendChild(groupBadge);
  }

  if (dependencyConflict) {
    decisionWarning.className = "decision-warning is-visible";
    decisionWarning.textContent = dependencyConflict;
  }

  if (status === "not_extracted") {
    decisionWarning.className = "decision-warning is-visible";
    decisionWarning.innerHTML = `此字段系统未抽取。若本产品不涉及此项权益，可点击「不适用 <span class="status-en">Skip / N/A</span>」跳过。<br>若确认该产品应有此权益但条款未约定，请填写最终值“不支持”并选择「接受 <span class="status-en">Accept</span>」。`;
  }

  updateActionButtons(decision?.status || status);
}

function updateActionButtons(selectedStatus) {
  Array.from(actionRow.querySelectorAll(".action-btn")).forEach((button) => {
    button.classList.toggle("is-selected", button.dataset.action === selectedStatus);
  });
}

function renderActionButtons() {
  actionRow.innerHTML = ACTION_LABELS.map((item) => `
    <button type="button" class="action-btn" data-action="${item.action}">
      ${item.zh}<span class="action-en">${item.en}</span>
    </button>
  `).join("");
}

function persistDecision(status) {
  const item = findItemById(state.selectedItemId);
  if (!item) return;
  const finalValue = finalValueInput.value.trim();
  const manualSource = buildManualSource(item, status, finalValue);
  state.decisions[item.item_id] = {
    item_id: item.item_id,
    coverage_name: item.coverage_name,
    status,
    final_value: finalValue,
    source_file: sourceFileSelect.value,
    source_page: sourcePageInput.value ? Number(sourcePageInput.value) : null,
    source_quote: sourceQuoteInput.value.trim(),
    manual_source: manualSource,
    reason_code: reasonCode.value,
    review_comment: reviewComment.value.trim()
  };
}

function buildSubmitPayload() {
  const items = getAllItems().map((item) => {
    const decision = getDecision(item.item_id);
    return {
      item_id: item.item_id,
      coverage_name: item.coverage_name,
      final_status: decision?.status || getEffectiveStatus(item),
      final_value: decision?.final_value ?? getEffectiveFinalValue(item),
      source_file: decision?.source_file || getEffectiveSourceMeta(item).source_file || "",
      source_page: decision?.source_page ?? getEffectiveSourceMeta(item).source_page ?? null,
      source_quote: decision?.source_quote || getEffectiveSourceMeta(item).source_quote || "",
      manual_source: decision?.manual_source || null,
      reason_code: decision?.reason_code || "",
      review_comment: decision?.review_comment || ""
    };
  });

  return {
    task: state.task.task,
    product: state.task.product,
    items
  };
}

function renderAll() {
  renderTopbar();
  renderFieldGroups();
  renderSources();
  renderLogicTrace();
  renderDecisionPanel();
}

async function handleSubmitImport() {
  state.submitState = "submitting";
  submitStatus.textContent = "提交中…";
  renderTopbar();
  try {
    await submitReview(buildSubmitPayload());
    state.submitState = "submitted";
    submitStatus.textContent = "已提交";
  } catch (error) {
    state.submitState = "failed";
    submitStatus.textContent = `提交失败：${error.message}`;
  }
  renderTopbar();
}

function bindEvents() {
  searchInput.addEventListener("input", (event) => {
    state.searchTerm = event.target.value;
    renderFieldGroups();
  });

  finalValueInput.addEventListener("input", () => {
    renderStandardHints(state.selectedItemId ? findItemById(state.selectedItemId) : null);
  });

  actionRow.addEventListener("click", (event) => {
    const button = event.target.closest(".action-btn");
    if (!button) return;
    persistDecision(button.dataset.action);
    renderAll();
  });

  saveDecision.addEventListener("click", () => {
    const item = findItemById(state.selectedItemId);
    if (!item) return;
    const fallbackStatus = getDecision(item.item_id)?.status || "modified";
    persistDecision(fallbackStatus);
    submitStatus.textContent = "已保存";
    renderSources();
    renderLogicTrace();
    renderDecisionPanel();
    renderFieldGroups();
    renderTopbar();
  });

  submitImport.addEventListener("click", handleSubmitImport);

  document.addEventListener("click", (event) => {
    const openBtn = event.target.closest("[data-open-path]");
    if (openBtn) {
      openLocalPath(openBtn.dataset.openPath);
      return;
    }
    const copyBtn = event.target.closest("[data-path]");
    if (copyBtn && copyBtn.classList.contains("file-copy-btn")) {
      copyText(copyBtn.dataset.path);
      return;
    }
    const hintChip = event.target.closest(".hint-chip");
    if (hintChip) {
      finalValueInput.value = hintChip.dataset.value;
      finalValueInput.focus();
    }
  });
}

function renderLoadError(error) {
  document.body.innerHTML = `
    <main style="padding:48px;font-family:-apple-system,BlinkMacSystemFont,'SF Pro Text','PingFang SC',sans-serif;">
      <div style="max-width:720px;margin:0 auto;background:#fff;border:1px solid rgba(29,29,31,.08);border-radius:18px;padding:32px;box-shadow:0 10px 40px rgba(0,0,0,.06);">
        <h1 style="margin:0 0 12px;font-size:28px;">人工复核工作台加载失败</h1>
        <p style="margin:0;color:#6e6e73;">页面未能完成初始化，请检查 mock 数据或接口返回结构。</p>
        <pre style="margin-top:20px;padding:16px;border-radius:10px;background:#fafafc;border:1px solid rgba(29,29,31,.08);white-space:pre-wrap;">${error.message}</pre>
      </div>
    </main>
  `;
}

async function bootstrap() {
  try {
    [state.task, state.standardValues] = await Promise.all([loadTask(), loadStandardValues()]);
    state.task.field_groups = state.task.field_groups || [];
    state.task.dependency_groups = state.task.dependency_groups || [];
    state.task.document_package = state.task.document_package || { files: [] };
    renderActionButtons();
    const firstItem = getAllItems()[0];
    state.selectedItemId = firstItem?.item_id || null;
    bindEvents();
    renderAll();
    await renderProductSelector();
  } catch (error) {
    renderLoadError(error);
  }
}

bootstrap();

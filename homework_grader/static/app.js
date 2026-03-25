const form = document.getElementById("grader-form");
const imageInput = document.getElementById("image");
const preview = document.getElementById("preview");
const resultPanel = document.getElementById("result-panel");
const scoreNode = document.getElementById("score");
const summaryNode = document.getElementById("summary");
const modelsNode = document.getElementById("models");

imageInput.addEventListener("change", () => {
  const [file] = imageInput.files;
  if (!file) {
    preview.classList.add("hidden");
    return;
  }

  const objectUrl = URL.createObjectURL(file);
  preview.src = objectUrl;
  preview.classList.remove("hidden");
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const formData = new FormData(form);

  summaryNode.textContent = "正在调用多个模型批改，请稍候...";
  modelsNode.innerHTML = "";
  scoreNode.textContent = "";
  resultPanel.classList.remove("hidden");

  try {
    const response = await fetch("/api/grade", {
      method: "POST",
      body: formData,
    });
    const payload = await response.json();

    if (!response.ok) {
      throw new Error(payload.detail || "请求失败");
    }

    const aggregate = payload.aggregate;
    scoreNode.textContent = `综合得分：${aggregate.average_score ?? "--"}`;
    summaryNode.textContent = aggregate.consensus_summary || "暂无总结";

    aggregate.model_results.forEach((result) => {
      const card = document.createElement("article");
      card.className = "model-card";

      const title = document.createElement("h3");
      title.textContent = `${result.provider} / ${result.model}`;
      card.appendChild(title);

      const summary = document.createElement("p");
      summary.textContent = result.parsed?.summary || result.error || "暂无内容";
      card.appendChild(summary);

      const list = document.createElement("div");
      list.className = "item-list";

      (result.parsed?.items || []).forEach((item) => {
        const row = document.createElement("section");
        row.className = "feedback-item";
        row.innerHTML = `
          <p><strong>题目：</strong>${item.question || "未识别"}</p>
          <p><strong>学生答案：</strong>${item.student_answer || "未识别"}</p>
          <p><strong>判断：</strong>${item.is_correct ? "正确" : "需订正"}</p>
          <p><strong>批改意见：</strong>${item.feedback || "无"}</p>
          <p><strong>讲解：</strong>${item.explanation || "无"}</p>
        `;
        list.appendChild(row);
      });

      card.appendChild(list);
      modelsNode.appendChild(card);
    });
  } catch (error) {
    summaryNode.textContent = error.message || "请求失败";
  }
});

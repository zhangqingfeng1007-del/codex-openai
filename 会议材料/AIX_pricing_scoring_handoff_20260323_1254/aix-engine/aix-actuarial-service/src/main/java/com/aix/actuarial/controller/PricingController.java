package com.aix.actuarial.controller;

import com.aix.actuarial.service.ActuarialPricingEngine;
import com.aix.actuarial.service.ActuarialPricingEngine.PricingResult;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.bind.annotation.*;

import java.util.*;

/**
 * 精算公允定价接口
 *
 * GET  /api/v1/actuarial/fair-price?productId=xxx&age=35&gender=male  （需DB配置）
 * POST /api/v1/actuarial/calculate                                     （手动参数，无需DB）
 */
@RestController
@RequestMapping("/api/v1/actuarial")
@RequiredArgsConstructor
public class PricingController {

    private final ActuarialPricingEngine pricingEngine;
    private final JdbcTemplate jdbcTemplate;

    /**
     * 获取指定产品的公允年保费（50万保额基准）。
     *
     * 成功响应（200）含：fairPremium、mortalityTable、ciTable、pricingRate、assumptionVersion
     *  → 所有定价结果必须携带假设元数据，保证可审计、可复现。
     *
     * 失败响应含：errorCode（NOT_CONFIGURED/TABLE_MISSING/CALC_ERROR/AGE_OUT_OF_RANGE/UNSUPPORTED_TYPE）
     *  → 调用方应根据 errorCode 决定是否降级，不得在失败时编造保费。
     */
    @GetMapping("/fair-price")
    public ResponseEntity<Map<String, Object>> getFairPrice(
            @RequestParam String productId,
            @RequestParam int age,
            @RequestParam(defaultValue = "male") String gender
    ) {
        if (age < 0 || age > 100) {
            return ResponseEntity.badRequest().body(Map.of(
                    "errorCode", ActuarialPricingEngine.ERR_AGE_OUT_OF_RANGE,
                    "error", "age 必须在 0~100 之间"));
        }
        if (!gender.equals("male") && !gender.equals("female")) {
            return ResponseEntity.badRequest().body(Map.of(
                    "errorCode", "INVALID_PARAM",
                    "error", "gender 必须为 male 或 female"));
        }

        PricingResult result = pricingEngine.calculateFull(productId, age, gender);

        if (!result.ok()) {
            int status = ActuarialPricingEngine.ERR_NOT_CONFIGURED.equals(result.errorCode()) ? 404 : 500;
            return ResponseEntity.status(status).body(Map.of(
                    "errorCode",  result.errorCode(),
                    "error",      translateErrorCode(result.errorCode()),
                    "productId",  productId));
        }

        Map<String, Object> resp = new LinkedHashMap<>();
        resp.put("productId",         productId);
        resp.put("age",               age);
        resp.put("gender",            gender);
        resp.put("fairPremium",       result.fairPremium());
        resp.put("sumAssured",        500000);
        resp.put("mortalityTable",    result.mortalityTable());
        resp.put("ciTable",           result.ciTable());
        resp.put("pricingRate",       result.pricingRate());
        resp.put("assumptionVersion", result.assumptionVersion());
        resp.put("note",              "50万保额、20年缴、终身保障基准");
        return ResponseEntity.ok(resp);
    }

    private String translateErrorCode(String code) {
        return switch (code) {
            case ActuarialPricingEngine.ERR_NOT_CONFIGURED   -> "产品未配置精算参数";
            case ActuarialPricingEngine.ERR_TABLE_MISSING    -> "精算表数据为空，请检查数据导入";
            case ActuarialPricingEngine.ERR_CALC_ERROR       -> "精算计算异常（附加费用率过高？）";
            case ActuarialPricingEngine.ERR_AGE_OUT_OF_RANGE -> "投保年龄超出范围（0~99岁）";
            case ActuarialPricingEngine.ERR_UNSUPPORTED_TYPE -> "当前仅支持 critical_illness 类型产品定价";
            default -> "未知错误：" + code;
        };
    }

    /**
     * 手动精算计算器（测试用，不需要数据库产品配置）
     *
     * POST /api/v1/actuarial/calculate
     * Body:
     * {
     *   "issueAge":      35,
     *   "gender":        "male",
     *   "pricingRate":   0.035,      // 预定利率
     *   "loadingRate":   0.25,       // 附加费用率
     *   "premPayPeriod": 20,         // 缴费年期
     *   "sumAssured":    500000,     // 保额（元）
     *   "maxAge":        105,        // 最高保障年龄（默认105）
     *   "benefitDeath":  true,       // 含身故
     *   "benefitCi":     true,       // 含重疾
     *   // ── 精算表来源（三选一）──
     *   "mortalityTableName": "CL1_1013_M",  // 从DB读死亡率表（可选）
     *   "ciTableName":        "CI25_Male",   // 从DB读重疾表（可选）
     *   "qdConstant":   0.003,       // 常数死亡率（无DB表时用于测试）
     *   "qciConstant":  0.005        // 常数重疾发病率（无DB表时用于测试）
     * }
     *
     * 返回：公允保费 + 完整计算过程（PVFB / 年金 / 各年度拆解）
     */
    @PostMapping("/calculate")
    public ResponseEntity<Map<String, Object>> manualCalculate(
            @RequestBody Map<String, Object> req
    ) {
        int    issueAge      = getInt(req,    "issueAge",      35);
        String gender        = getString(req, "gender",        "male");
        double pricingRate   = getDbl(req,    "pricingRate",   0.035);
        double loadingRate   = getDbl(req,    "loadingRate",   0.25);
        int    premPayPeriod = getInt(req,    "premPayPeriod", 20);
        int    sumAssured    = getInt(req,    "sumAssured",    500000);
        int    maxAge        = getInt(req,    "maxAge",        105);
        boolean benefitDeath = getBool(req,   "benefitDeath",  true);
        boolean benefitCi    = getBool(req,   "benefitCi",     true);

        // 校验
        if (issueAge < 0 || issueAge >= maxAge)
            return ResponseEntity.badRequest().body(Map.of("error", "issueAge 超出范围"));
        if (pricingRate <= 0 || pricingRate > 0.2)
            return ResponseEntity.badRequest().body(Map.of("error", "pricingRate 应在 0~0.2 之间"));
        if (loadingRate < 0 || loadingRate >= 1)
            return ResponseEntity.badRequest().body(Map.of("error", "loadingRate 应在 0~1 之间"));

        int T = maxAge - issueAge;
        double v = 1.0 / (1.0 + pricingRate);

        // 读取死亡率数组
        double[] qd  = buildQxArray(req, "mortalityTableName", "qdConstant",
                                    issueAge, T, benefitDeath ? 0.002 : 0.0);
        // 读取重疾发病率数组
        double[] qci = buildQxArray(req, "ciTableName", "qciConstant",
                                    issueAge, T, benefitCi ? 0.003 : 0.0);

        // 逐年计算
        double pvfb       = 0;
        double annuityDue = 0;
        double pvLoading  = 0;
        double px         = 1.0;

        List<Map<String, Object>> yearlyDetail = new ArrayList<>();

        for (int t = 0; t < T; t++) {
            double vt       = Math.pow(v, t + 1);
            double vtStart  = Math.pow(v, t);

            double qdT  = benefitDeath ? qd[t]  : 0.0;
            double qciT = benefitCi    ? qci[t] : 0.0;
            double benefitRate = qdT + qciT;

            double pvfbT = px * benefitRate * sumAssured * vt;
            pvfb += pvfbT;

            double annT = 0, loadT = 0;
            if (t < premPayPeriod) {
                annT   = px * vtStart;
                loadT  = px * loadingRate * vtStart;
                annuityDue += annT;
                pvLoading  += loadT;
            }

            // 只记录前30年 + 最后5年，避免返回数据过大
            int age = issueAge + t;
            if (t < 30 || t >= T - 5) {
                Map<String, Object> row = new LinkedHashMap<>();
                row.put("age",   age);
                row.put("t",     t + 1);
                row.put("px",    round4(px));
                row.put("qd",    round6(qdT));
                row.put("qci",   round6(qciT));
                row.put("pvfbT", round2(pvfbT));
                row.put("annT",  round4(annT));
                yearlyDetail.add(row);
            }

            px *= Math.max(0, 1.0 - qdT - qciT);
        }

        double denominator = annuityDue - pvLoading;
        double gp = denominator > 0 ? pvfb / denominator : -1;

        // 构建返回结果
        Map<String, Object> result = new LinkedHashMap<>();
        result.put("fairPremium",    gp > 0 ? Math.round(gp * 100.0) / 100.0 : null);
        result.put("error",          gp <= 0 ? "分母为0，请检查loadingRate是否过高" : null);

        Map<String, Object> breakdown = new LinkedHashMap<>();
        breakdown.put("pvfb",        round2(pvfb));
        breakdown.put("annuityDue",  round4(annuityDue));
        breakdown.put("pvLoading",   round4(pvLoading));
        breakdown.put("denominator", round4(denominator));
        breakdown.put("gp_formula",  "PVFB / (AnnuityDue - PV_Loading)");
        breakdown.put("gp_calc",     String.format("%.2f / %.4f = %.2f", pvfb, denominator, gp));
        result.put("breakdown",      breakdown);

        Map<String, Object> params = new LinkedHashMap<>();
        params.put("issueAge",      issueAge);
        params.put("gender",        gender);
        params.put("pricingRate",   pricingRate);
        params.put("loadingRate",   loadingRate);
        params.put("premPayPeriod", premPayPeriod);
        params.put("sumAssured",    sumAssured);
        params.put("maxAge",        maxAge);
        params.put("benefitDeath",  benefitDeath);
        params.put("benefitCi",     benefitCi);
        params.put("qdSource",      req.containsKey("mortalityTableName") ? req.get("mortalityTableName") : "常数=" + req.getOrDefault("qdConstant", 0.002));
        params.put("qciSource",     req.containsKey("ciTableName") ? req.get("ciTableName") : "常数=" + req.getOrDefault("qciConstant", 0.003));
        result.put("inputParams",   params);
        result.put("yearlyDetail",  yearlyDetail);

        return ResponseEntity.ok(result);
    }

    // ── 辅助方法 ──────────────────────────────────────────────────────────────

    private double[] buildQxArray(Map<String, Object> req, String tableKey, String constKey,
                                   int startAge, int length, double defaultConst) {
        double[] arr = new double[length];
        String tableName = getString(req, tableKey, "");
        double constRate = getDbl(req, constKey, -1);

        if (!tableName.isEmpty()) {
            // 优先从DB读
            try {
                List<Map<String, Object>> rows = jdbcTemplate.queryForList(
                    "SELECT age, qx FROM actuarial_qx_table WHERE table_name=? AND age>=? AND age<? ORDER BY age",
                    tableName, startAge, startAge + length
                );
                if (rows.isEmpty()) {
                    rows = jdbcTemplate.queryForList(
                        "SELECT age, qx FROM actuarial_ci_table WHERE table_name=? AND age>=? AND age<? ORDER BY age",
                        tableName, startAge, startAge + length
                    );
                }
                for (Map<String, Object> row : rows) {
                    int idx = ((Number) row.get("age")).intValue() - startAge;
                    if (idx >= 0 && idx < length) arr[idx] = ((Number) row.get("qx")).doubleValue();
                }
                return arr;
            } catch (Exception ignored) {}
        }

        // 用常数率填充（测试模式）
        double rate = constRate >= 0 ? constRate : defaultConst;
        Arrays.fill(arr, rate);
        return arr;
    }

    private int    getInt(Map<String,Object> m, String k, int def)     { return m.containsKey(k) ? ((Number)m.get(k)).intValue() : def; }
    private double getDbl(Map<String,Object> m, String k, double def)  { return m.containsKey(k) ? ((Number)m.get(k)).doubleValue() : def; }
    private String getString(Map<String,Object> m, String k, String d) { return m.containsKey(k) ? String.valueOf(m.get(k)) : d; }
    private boolean getBool(Map<String,Object> m, String k, boolean d) { return m.containsKey(k) ? Boolean.parseBoolean(String.valueOf(m.get(k))) : d; }
    private double round2(double v) { return Math.round(v * 100.0) / 100.0; }
    private double round4(double v) { return Math.round(v * 10000.0) / 10000.0; }
    private double round6(double v) { return Math.round(v * 1000000.0) / 1000000.0; }

    /**
     * 批量查询（产品评分时批量调用优化）
     * POST /api/v1/actuarial/fair-price/batch
     * Body: [{"productId":"xxx","age":35,"gender":"male"}, ...]
     */
    @PostMapping("/fair-price/batch")
    public ResponseEntity<Object> batchFairPrice(
            @RequestBody java.util.List<Map<String, Object>> requests
    ) {
        if (requests == null || requests.size() > 100) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "批量请求数量限制 1~100"));
        }
        var results = requests.stream().map(req -> {
            String pid = String.valueOf(req.get("productId"));
            int a = req.containsKey("age") ? ((Number) req.get("age")).intValue() : 35;
            String g = req.getOrDefault("gender", "male").toString();
            PricingResult r = pricingEngine.calculateFull(pid, a, g);
            return Map.of(
                    "productId",   pid,
                    "fairPremium", r.ok() ? r.fairPremium() : 0,
                    "available",   r.ok(),
                    "errorCode",   r.ok() ? ActuarialPricingEngine.ERR_OK : r.errorCode()
            );
        }).toList();
        return ResponseEntity.ok(results);
    }
}

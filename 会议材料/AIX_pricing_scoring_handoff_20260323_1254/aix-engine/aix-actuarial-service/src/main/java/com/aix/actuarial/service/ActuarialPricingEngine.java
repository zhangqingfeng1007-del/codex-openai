package com.aix.actuarial.service;

import com.aix.actuarial.model.entity.ProductActuarialConfigEntity;
import com.aix.actuarial.repository.ProductActuarialConfigRepository;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Optional;

/**
 * 精算公允定价引擎
 *
 * 核心公式（等值原理）：
 *   GP = PVFB / (AnnuityDue - PV_Loading)
 *
 *   PVFB       = Σ px_t × (qd_t + qci_t) × SA × v^t    未来给付现值
 *   AnnuityDue = Σ[t=0..PPP-1] px_t × v^t               缴费期期初年金现值
 *   PV_Loading = loading_rate × AnnuityDue               附加费用现值
 *
 *   px_t = Π[i=0..t-1] (1 - qd_i - qci_i)               期初生存概率
 *   v    = 1 / (1 + pricingRate)                          折现因子
 *   T    = 105 - issueAge（终身保障）
 *
 * 精算假设均来自数据库 product_actuarial_config，所有输出结果
 * 均携带 assumptionVersion，确保可审计、可复现。
 */
@Slf4j
@Service
@RequiredArgsConstructor
public class ActuarialPricingEngine {

    // ── 错误码常量（供调用方判断降级策略） ──────────────────────────────────────
    public static final String ERR_OK                = "OK";
    public static final String ERR_NOT_CONFIGURED    = "NOT_CONFIGURED";   // 产品无精算配置
    public static final String ERR_TABLE_MISSING     = "TABLE_MISSING";    // 精算表数据为空
    public static final String ERR_CALC_ERROR        = "CALC_ERROR";       // 分母为0等计算异常
    public static final String ERR_AGE_OUT_OF_RANGE  = "AGE_OUT_OF_RANGE"; // 年龄超出范围
    public static final String ERR_UNSUPPORTED_TYPE  = "UNSUPPORTED_TYPE"; // 不支持的产品类型

    /**
     * 定价结果封装 — 含错误码和假设元数据，供审计和 AI 评分模块使用。
     *
     * @param fairPremium       公允年保费（errorCode=OK 时有效，否则为 -1）
     * @param errorCode         OK 或以上 ERR_* 常量之一
     * @param mortalityTable    使用的死亡率表名
     * @param ciTable           使用的重疾发病率表名
     * @param pricingRate       使用的预定利率
     * @param assumptionVersion 精算数据版本号（如 "2017"）
     */
    public record PricingResult(
            double  fairPremium,
            String  errorCode,
            String  mortalityTable,
            String  ciTable,
            double  pricingRate,
            String  assumptionVersion
    ) {
        public boolean ok() { return ERR_OK.equals(errorCode); }

        /** 快速构建错误结果 */
        static PricingResult error(String code) {
            return new PricingResult(-1, code, null, null, 0, null);
        }
    }

    private final ProductActuarialConfigRepository configRepo;
    private final JdbcTemplate jdbcTemplate;

    /**
     * 向后兼容接口：返回公允年保费，失败时返回 -1。
     * 内部调用 calculateFull()。
     */
    @Cacheable(value = "fairPremium", key = "#productId + '_' + #issueAge + '_' + #gender")
    public double calculate(String productId, int issueAge, String gender) {
        return calculateFull(productId, issueAge, gender).fairPremium();
    }

    /**
     * 完整定价接口：返回 PricingResult，含公允保费、错误码和假设元数据。
     * 调用方应根据 errorCode 决定是否降级，不得在失败时编造保费。
     *
     * @param productId 产品ID（my_ensure.cmb_product.product_id）
     * @param issueAge  投保年龄（0~99）
     * @param gender    "male" | "female"
     */
    public PricingResult calculateFull(String productId, int issueAge, String gender) {
        if (issueAge < 0 || issueAge > 99) {
            return PricingResult.error(ERR_AGE_OUT_OF_RANGE);
        }

        Optional<ProductActuarialConfigEntity> cfgOpt = configRepo.findById(productId);
        if (cfgOpt.isEmpty()) {
            log.info("product_actuarial_config 未配置: {}", productId);
            return PricingResult.error(ERR_NOT_CONFIGURED);
        }
        ProductActuarialConfigEntity cfg = cfgOpt.get();

        // 当前仅支持 critical_illness；其他类型预留策略扩展
        if (!"critical_illness".equalsIgnoreCase(cfg.getProductType())) {
            log.warn("不支持的产品类型 product_type={} productId={}", cfg.getProductType(), productId);
            return PricingResult.error(ERR_UNSUPPORTED_TYPE);
        }

        boolean isMale  = "male".equalsIgnoreCase(gender);
        String qxTable  = isMale ? cfg.getMortalityTableM() : cfg.getMortalityTableF();
        String ciTable  = isMale ? cfg.getCiTableM()        : cfg.getCiTableF();
        double v        = 1.0 / (1.0 + cfg.getPricingRate());
        double loading  = cfg.getLoadingRate();
        int    sa       = cfg.getSumAssured();
        int    ppp      = cfg.getPremPayPeriod();
        int    T        = 105 - issueAge;

        double[] qd  = loadQxArray(qxTable, issueAge, T);
        double[] qci = cfg.getBenefitCi() ? loadQxArray(ciTable, issueAge, T) : new double[T];

        // 精算表为全零视为数据缺失，不得用0代替真实发生率
        if (cfg.getBenefitDeath() && !hasNonZeroData(qd)) {
            log.warn("死亡率表数据为空 table={} productId={}", qxTable, productId);
            return new PricingResult(-1, ERR_TABLE_MISSING, qxTable, ciTable,
                                     cfg.getPricingRate(), cfg.getAssumptionVersion());
        }
        if (cfg.getBenefitCi() && !hasNonZeroData(qci)) {
            log.warn("重疾发病率表数据为空 table={} productId={}", ciTable, productId);
            return new PricingResult(-1, ERR_TABLE_MISSING, qxTable, ciTable,
                                     cfg.getPricingRate(), cfg.getAssumptionVersion());
        }

        // 逐年精算计算
        double pvfb      = 0;
        double annuityDue = 0;
        double pvLoading  = 0;
        double px = 1.0;

        for (int t = 0; t < T; t++) {
            double vt = Math.pow(v, t + 1);

            double benefitRate = 0;
            if (cfg.getBenefitDeath()) benefitRate += qd[t];
            if (cfg.getBenefitCi())    benefitRate += qci[t];
            pvfb += px * benefitRate * sa * vt;

            if (t < ppp) {
                double vtStart = Math.pow(v, t);
                annuityDue += px * vtStart;
                pvLoading  += px * loading * vtStart;
            }

            px *= Math.max(0, 1.0 - qd[t] - qci[t]);
        }

        double denominator = annuityDue - pvLoading;
        if (denominator <= 0) {
            log.warn("定价分母为0（loadingRate过高？）productId={} loadingRate={}", productId, loading);
            return new PricingResult(-1, ERR_CALC_ERROR, qxTable, ciTable,
                                     cfg.getPricingRate(), cfg.getAssumptionVersion());
        }

        double gp = Math.round(pvfb / denominator * 100.0) / 100.0;
        log.debug("fair-price OK product={} age={} gender={} PVFB={} GP={} ver={}",
                productId, issueAge, gender, String.format("%.2f", pvfb),
                String.format("%.2f", gp), cfg.getAssumptionVersion());

        return new PricingResult(gp, ERR_OK, qxTable, ciTable,
                                 cfg.getPricingRate(), cfg.getAssumptionVersion());
    }

    /**
     * 从数据库加载指定年龄起的 qx 数组（长度=T）。
     * 优先查 actuarial_qx_table，回退查 actuarial_ci_table；
     * 表不存在时全返回0（由调用方通过 hasNonZeroData 检测）。
     */
    private double[] loadQxArray(String tableName, int startAge, int length) {
        double[] arr = new double[length];
        try {
            List<Map<String, Object>> rows = jdbcTemplate.queryForList(
                    "SELECT age, qx FROM actuarial_qx_table WHERE table_name = ? AND age >= ? AND age < ? ORDER BY age",
                    tableName, startAge, startAge + length);
            if (rows.isEmpty()) {
                rows = jdbcTemplate.queryForList(
                        "SELECT age, qx FROM actuarial_ci_table WHERE table_name = ? AND age >= ? AND age < ? ORDER BY age",
                        tableName, startAge, startAge + length);
            }
            for (Map<String, Object> row : rows) {
                int idx = ((Number) row.get("age")).intValue() - startAge;
                if (idx >= 0 && idx < length)
                    arr[idx] = ((Number) row.get("qx")).doubleValue();
            }
        } catch (Exception e) {
            log.warn("读取精算表失败 table={}: {}", tableName, e.getMessage());
        }
        return arr;
    }

    private boolean hasNonZeroData(double[] arr) {
        return Arrays.stream(arr).anyMatch(v -> v > 0);
    }
}

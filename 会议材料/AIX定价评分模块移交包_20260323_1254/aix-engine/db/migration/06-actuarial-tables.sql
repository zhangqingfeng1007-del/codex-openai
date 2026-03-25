-- 精算公允定价数据库表
-- 数据库：aix_engine
-- 执行方式：docker compose exec -T mysql mysql -u root -proot_secret aix_engine < db/migration/06-actuarial-tables.sql

USE aix_engine;

-- 1. 产品精算配置（每款产品一行，由管理后台维护）
CREATE TABLE IF NOT EXISTS product_actuarial_config (
  product_id          VARCHAR(50)    NOT NULL COMMENT '对应 my_ensure.cmb_product.product_id',
  -- 精算假设（所有输出结果均须携带以下版本信息，保证可审计、可复现）
  assumption_version  VARCHAR(20)    NOT NULL DEFAULT '2017' COMMENT '精算数据版本号（如 2017、2013），随结果一并输出，不得省略',
  product_type        VARCHAR(30)    NOT NULL DEFAULT 'critical_illness' COMMENT '产品类型，用于精算策略选择：critical_illness/medical/annuity（预留扩展）',
  -- 精算表引用
  mortality_table_m   VARCHAR(50)    NOT NULL DEFAULT 'CL1_1013_M' COMMENT '男性死亡率表名（actuarial_qx_table.table_name）',
  mortality_table_f   VARCHAR(50)    NOT NULL DEFAULT 'CL2_1013_F' COMMENT '女性死亡率表名',
  ci_table_m          VARCHAR(50)    NOT NULL DEFAULT 'CI25_Male'  COMMENT '男性重疾发病率表名（actuarial_ci_table.table_name）',
  ci_table_f          VARCHAR(50)    NOT NULL DEFAULT 'CI25_Female' COMMENT '女性重疾发病率表名',
  -- 精算参数
  pricing_rate        DECIMAL(6,4)   NOT NULL DEFAULT 0.0350 COMMENT '预定利率（如0.035=3.5%，传统险监管上限3.5%）',
  loading_rate        DECIMAL(6,4)   NOT NULL DEFAULT 0.2500 COMMENT '附加费用率（期交监管上限25%）',
  -- 保障责任开关
  benefit_death       TINYINT(1)     NOT NULL DEFAULT 1 COMMENT '是否含身故保障',
  benefit_ci          TINYINT(1)     NOT NULL DEFAULT 1 COMMENT '是否含重疾保障',
  benefit_minor_ci    TINYINT(1)     NOT NULL DEFAULT 0 COMMENT '是否含轻症保障',
  benefit_waiver      TINYINT(1)     NOT NULL DEFAULT 0 COMMENT '是否含保费豁免（当前版本未实现，预留）',
  benefit_multiple_ci TINYINT(1)     NOT NULL DEFAULT 0 COMMENT '是否支持多次重疾赔付（当前版本未实现，预留）',
  -- 计算基准
  sum_assured         INT            NOT NULL DEFAULT 500000 COMMENT '定价基准保额（元）',
  prem_pay_period     INT            NOT NULL DEFAULT 20    COMMENT '缴费年期（年）',
  updated_at          DATETIME       NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (product_id),
  KEY idx_product_type (product_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='产品精算定价参数配置表，由管理后台维护；assumption_version 随每次定价结果输出，确保可审计';

-- 2. 死亡率表（中国精算师协会标准生命表）
CREATE TABLE IF NOT EXISTS actuarial_qx_table (
  table_name  VARCHAR(50)    NOT NULL COMMENT '表名，如 CL1_1013_M、CL2_1013_F',
  age         SMALLINT       NOT NULL COMMENT '年龄（0~105）',
  qx          DECIMAL(12,10) NOT NULL COMMENT '当年死亡概率',
  PRIMARY KEY (table_name, age)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='精算死亡率表；CL1_1013_M=2013男性经验表，CL2_1013_F=2013女性经验表';

-- 3. 重疾发病率表
CREATE TABLE IF NOT EXISTS actuarial_ci_table (
  table_name  VARCHAR(50)    NOT NULL COMMENT '表名，如 CI25_Male、CI25_Female',
  age         SMALLINT       NOT NULL COMMENT '年龄',
  qx          DECIMAL(12,10) NOT NULL COMMENT '重疾发病率（当年）',
  PRIMARY KEY (table_name, age)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='重疾险发病率表；CI25_Male/CI25_Female=25种重疾合计发病率';

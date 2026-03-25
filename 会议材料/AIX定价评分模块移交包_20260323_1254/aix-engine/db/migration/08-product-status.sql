-- ========== 08-product-status.sql ==========
-- 为 cmb_product 表添加产品状态和数据来源字段
-- 执行前提：06-actuarial-tables.sql 已执行
-- 影响表：aix_engine.cmb_product（注意：表实际在 my_ensure 库）
-- ============================================

-- ⚠️ cmb_product 在 my_ensure 库，需切换
USE my_ensure;

-- 1. 添加 product_status 字段（通过 information_schema 判断是否已存在）
DROP PROCEDURE IF EXISTS _add_product_status;
DELIMITER $$
CREATE PROCEDURE _add_product_status()
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'my_ensure'
      AND TABLE_NAME   = 'cmb_product'
      AND COLUMN_NAME  = 'product_status'
  ) THEN
    ALTER TABLE cmb_product
      ADD COLUMN product_status ENUM(
        'STANDARDIZED',      -- 责任已映射至标准库，可用于规则/展示
        'PENDING_INFO',      -- 基础信息已入库，部分责任待补充
        'PENDING_ACTUARIAL', -- 数据已录入，精算参数待核对
        'PENDING_RELEASE',   -- 数据+精算均就绪，待前台开放
        'RELEASED',          -- 当前对用户可见可推荐
        'OFFLINE'            -- 历史产品，保留数据但不推荐
      ) NOT NULL DEFAULT 'PENDING_INFO'
      COMMENT '产品状态：只有 RELEASED 的产品进入推荐/评分/精算链路'
      AFTER product_name;
  END IF;
END$$
DELIMITER ;
CALL _add_product_status();
DROP PROCEDURE IF EXISTS _add_product_status;

-- 2. 添加 data_source 字段
DROP PROCEDURE IF EXISTS _add_data_source;
DELIMITER $$
CREATE PROCEDURE _add_data_source()
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = 'my_ensure'
      AND TABLE_NAME   = 'cmb_product'
      AND COLUMN_NAME  = 'data_source'
  ) THEN
    ALTER TABLE cmb_product
      ADD COLUMN data_source ENUM(
        'NEW_DB',    -- 新标准库（my_ensure，当前主数据源）
        'LEGACY_DB', -- 老数据库（二期映射接入）
        'EXCEL'      -- Excel 管理表（三期治理后纳入）
      ) NOT NULL DEFAULT 'NEW_DB'
      COMMENT '数据来源：新库 > 老库 > Excel，优先级依次降低'
      AFTER product_status;
  END IF;
END$$
DELIMITER ;
CALL _add_data_source();
DROP PROCEDURE IF EXISTS _add_data_source;

-- 3. 将已有重疾险产品设为 RELEASED（这些是一期已确认使用的产品）
-- product_id 来自 ~/Desktop/重疾险产品数据.sql 中确认在销的产品
UPDATE cmb_product
SET product_status = 'RELEASED', data_source = 'NEW_DB'
WHERE product_id IN (
  '1010003919',  -- 招商信诺爱享无忧（重疾险，在销）
  '1010004022',  -- 金小葵少儿重疾险（在销）
  '1170004238',  -- 中意悦享安康重疾险（在销）
  '1010004001'   -- 招商信诺爱享未来重疾险（在销）
);

-- 4. 将已停售但保留做回归测试的产品设为 OFFLINE
UPDATE cmb_product
SET product_status = 'OFFLINE', data_source = 'NEW_DB'
WHERE product_id IN (
  '1010003564'   -- 招商信诺爱享康健2023（已停售，保留做精算回归）
);

-- ========== 验证 ==========
SELECT
  product_status,
  data_source,
  COUNT(*) AS cnt
FROM cmb_product
WHERE product_id IN ('1010003919','1010004022','1170004238','1010004001','1010003564')
GROUP BY product_status, data_source;

-- 预期：
--   RELEASED  NEW_DB  4
--   OFFLINE   NEW_DB  1

/**
 * MDM 主数据字典 composable
 *
 * 提供带缓存的 MDM 字典数据加载，供业务页面的下拉/选择器使用。
 * 所有数据在首次调用时从后端 /mdm/* API 加载，缓存到模块级变量，
 * 后续调用直接返回缓存，避免重复请求。
 *
 * 用法：
 *   import { useMdmDict } from '@/utils/mdmDict'
 *   const { statusOptions, unitOptions } = useMdmDict()
 *   // 在 a-select 中使用 :options="statusOptions('sample')"
 */
import { ref } from 'vue'
import * as mdmApi from '@/api/mdm'

// ──────────────────────────────────────────────────────────────
// 模块级缓存
// ──────────────────────────────────────────────────────────────
// 不带过滤参数的字典：单值缓存
const _cache = {
  sampleTypes: null,
  locations: null,
  containers: null,
  logisticsTypes: null,
  equipmentTemplates: null,
  materialCategories: null,
  properties: null,
  testMethods: null,
  ghsClasses: null,
  standards: null,
}

// 带 domain/dimension 过滤参数的字典：按 子键 缓存
// 结构: { statusCodes: { sample: [...], equipment: [...] }, dimensions: {...}, ... }
const _keyedCache = {
  statusCodes: {},
  dimensions: {},
  units: {},
  classifications: {},
}

const _loading = {}
const _keyedLoading = {}

/**
 * 通用加载器：带缓存 + 防重入（不带过滤参数）
 */
async function _load(key, loader) {
  if (_cache[key]) return _cache[key]
  if (_loading[key]) return _loading[key]
  _loading[key] = (async () => {
    try {
      // axios 响应拦截器已剥一层（返回 resp.data），此处 res 即后端响应体本身
      const data = await loader()
      const list = Array.isArray(data) ? data : (data[_getResponseKey(key)] || [])
      _cache[key] = list
      return list
    } catch (e) {
      console.warn(`加载 MDM 字典 ${key} 失败:`, e)
      // 失败不写永久缓存，仅本次返回空；下次调用会重新请求（自愈），
      // 避免瞬时故障被固化成整会话的空数据导致下拉持续走本地兜底。
      return []
    } finally {
      delete _loading[key]
    }
  })()
  return _loading[key]
}

/**
 * 带 subKey（domain/dimension）的加载器：按 subKey 独立缓存，避免互相污染
 */
async function _loadKeyed(key, subKey, loader) {
  const bucket = _keyedCache[key]
  if (bucket[subKey]) return bucket[subKey]
  const loadingKey = `${key}:${subKey}`
  if (_keyedLoading[loadingKey]) return _keyedLoading[loadingKey]
  _keyedLoading[loadingKey] = (async () => {
    try {
      // axios 响应拦截器已剥一层（返回 resp.data），此处 res 即后端响应体本身
      const data = await loader()
      const list = Array.isArray(data) ? data : (data[_getResponseKey(key)] || [])
      bucket[subKey] = list
      return list
    } catch (e) {
      console.warn(`加载 MDM 字典 ${key} (subKey=${subKey}) 失败:`, e)
      // 失败不写永久缓存，仅本次返回空；下次调用会重新请求（自愈）
      return []
    } finally {
      delete _keyedLoading[loadingKey]
    }
  })()
  return _keyedLoading[loadingKey]
}

function _getResponseKey(key) {
  const map = {
    statusCodes: 'status_codes',
    dimensions: 'dimensions',
    units: 'units',
    classifications: 'classifications',
    sampleTypes: 'sample_types',
    locations: 'locations',
    containers: 'containers',
    logisticsTypes: 'logistics_types',
    equipmentTemplates: 'equipment_templates',
    materialCategories: 'material_categories',
    properties: 'properties',
    testMethods: 'test_methods',
    ghsClasses: 'ghs_classes',
    standards: 'standards',
  }
  return map[key] || key
}

/**
 * 清除指定缓存或全部缓存
 */
export function clearMdmCache(key) {
  if (key) {
    if (key in _cache) {
      _cache[key] = null
    } else if (key in _keyedCache) {
      _keyedCache[key] = {}
    }
  } else {
    Object.keys(_cache).forEach(k => { _cache[k] = null })
    Object.keys(_keyedCache).forEach(k => {
      _keyedCache[k] = {}
    })
  }
}

// ──────────────────────────────────────────────────────────────
// composable
// ──────────────────────────────────────────────────────────────
export function useMdmDict() {
  /**
   * 状态码选项（按 domain 过滤）
   * @param {string} domain - sample/equipment/order/test_task/task/idea/case/run/qc_status/material_request/tool_health
   * @returns {Promise<Array<{label,value}>>}
   */
  async function statusOptions(domain) {
    const list = await _loadKeyed('statusCodes', domain || '__all__', () => mdmApi.listStatusCodes(domain))
    return list
      .filter(item => item.is_active)
      .map(item => ({ label: item.label, value: item.code }))
  }

  /**
   * 维度选项（按 domain 过滤）
   * @param {string} domain - priority/role/project_stage/execution_mode/data_source_type/storage_condition/agent_role/autonomy_level/version_type/cost_category/material_request_type/data_source/sample_source_type/committee_type/evidence_source/trigger_code/target_application/project_type/supplier_type
   */
  async function dimensionOptions(domain) {
    const list = await _loadKeyed('dimensions', domain || '__all__', () => mdmApi.listDimensions(domain))
    return list
      .filter(item => item.is_active)
      .map(item => ({ label: item.label, value: item.code }))
  }

  /**
   * 单位选项（按 dimension 过滤）
   * @param {string} dimension - mass/volume/concentration/temperature/pressure/conductivity/voltage/specific_capacity/energy/density/time/rotational_speed
   */
  async function unitOptions(dimension = '') {
    const list = await _loadKeyed('units', dimension || '__all__', () => mdmApi.listUnits(dimension))
    return list
      .filter(item => item.is_active)
      .map(item => ({
        label: `${item.name} (${item.symbol})`,
        value: item.unit_code,
        symbol: item.symbol,
      }))
  }

  /**
   * 分类码选项（按 domain 过滤）
   * @param {string} domain - experiment_type/material/equipment/process_type
   */
  async function classificationOptions(domain) {
    const list = await _loadKeyed('classifications', domain || '__all__', () => mdmApi.listClassifications(domain))
    return list
      .filter(item => item.is_active)
      .map(item => ({ label: item.label, value: item.code }))
  }

  /**
   * 样品类型选项
   */
  async function sampleTypeOptions() {
    const list = await _load('sampleTypes', () => mdmApi.listSampleTypes())
    return list
      .filter(item => item.is_active)
      .map(item => ({ label: item.name, value: item.type_code }))
  }

  /**
   * 位置选项
   */
  async function locationOptions() {
    const list = await _load('locations', () => mdmApi.listLocations())
    return list
      .filter(item => item.is_active)
      .map(item => ({ label: item.name, value: item.location_id }))
  }

  /**
   * 容器选项
   */
  async function containerOptions() {
    const list = await _load('containers', () => mdmApi.listContainers())
    return list
      .filter(item => item.is_active)
      .map(item => ({ label: item.name, value: item.container_code }))
  }

  /**
   * 物流类型选项
   */
  async function logisticsTypeOptions() {
    const list = await _load('logisticsTypes', () => mdmApi.listLogisticsTypes())
    return list
      .filter(item => item.is_active)
      .map(item => ({ label: item.name, value: item.type_code }))
  }

  /**
   * 设备模板选项
   */
  async function equipmentTemplateOptions() {
    const list = await _load('equipmentTemplates', () => mdmApi.listEquipmentTemplates())
    return list
      .filter(item => item.is_active)
      .map(item => ({ label: item.name, value: item.template_code }))
  }

  /**
   * 物料分类选项
   */
  async function materialCategoryOptions() {
    const list = await _load('materialCategories', () => mdmApi.listMaterialCategories())
    return list
      .filter(item => item.is_active)
      .map(item => ({ label: item.name, value: item.category_code }))
  }

  /**
   * 特性选项
   */
  async function propertyOptions() {
    const list = await _load('properties', () => mdmApi.listProperties())
    return list
      .filter(item => item.is_active)
      .map(item => ({ label: item.name, value: item.property_id }))
  }

  /**
   * 测试方法选项
   */
  async function testMethodOptions() {
    const list = await _load('testMethods', () => mdmApi.listTestMethods())
    return list
      .filter(item => item.is_active)
      .map(item => ({ label: item.name, value: item.method_id }))
  }

  /**
   * GHS 危害分类选项
   */
  async function ghsClassOptions() {
    const list = await _load('ghsClasses', () => mdmApi.listGhsClasses())
    return list
      .filter(item => item.is_active)
      .map(item => ({ label: item.label, value: item.ghs_code }))
  }

  /**
   * 方法标准选项
   */
  async function standardOptions() {
    const list = await _load('standards', () => mdmApi.listStandards())
    return list
      .filter(item => item.is_active)
      .map(item => ({ label: item.name, value: item.standard_code }))
  }

  return {
    statusOptions,
    dimensionOptions,
    unitOptions,
    classificationOptions,
    sampleTypeOptions,
    locationOptions,
    containerOptions,
    logisticsTypeOptions,
    equipmentTemplateOptions,
    materialCategoryOptions,
    propertyOptions,
    testMethodOptions,
    ghsClassOptions,
    standardOptions,
    clearMdmCache,
  }
}

// ──────────────────────────────────────────────────────────────
// 单位符号工具：从 MDM 主数据加载单位符号，供列标题等场景使用
// ──────────────────────────────────────────────────────────────

/**
 * 各维度的业务首选单位 unit_code（符号从 MDM 获取，单位码由业务约定）
 * 当 MDM 中对应单位记录存在时，使用 MDM 的 symbol；否则回退到默认符号。
 */
const PREFERRED_UNIT_CODE = {
  mass: 'kg',
  volume: 'mL',
  concentration: 'mol/L',
  temperature: 'C',
  pressure: 'MPa',
  conductivity: 'S/cm',
  voltage: 'V',
  specific_capacity: 'mAh/g',
  energy: 'eV',
  density: 'g/cm3',
  time: 'h',
  rotational_speed: 'rpm',
  frequency: 'Hz',
  current: 'A',
  // 复合维度（MDM 中若有对应记录则用 MDM symbol，否则回退到 FALLBACK_SYMBOL）
  energy_per_atom: 'eV/atom',
  energy_density: 'Wh/kg',
  power_density: 'W/kg',
  thermal_conductivity: 'W/mK',
  heat_generation: 'W/m3',
  modulus: 'GPa',
  activation_energy: 'kJ/mol',
  rate_constant: '1/s',
  temperature_delta: 'K',
  inverse_time: '1/s',
}

/** MDM 加载失败时的回退符号（与 PREFERRED_UNIT_CODE 对应） */
const FALLBACK_SYMBOL = {
  mass: 'kg',
  volume: 'mL',
  concentration: 'mol/L',
  temperature: '°C',
  pressure: 'MPa',
  conductivity: 'S/cm',
  voltage: 'V',
  specific_capacity: 'mAh/g',
  energy: 'eV',
  density: 'g/cm³',
  time: 'h',
  rotational_speed: 'rpm',
  frequency: 'Hz',
  current: 'A',
  // 复合维度回退符号
  energy_per_atom: 'eV/atom',
  energy_density: 'Wh/kg',
  power_density: 'W/kg',
  thermal_conductivity: 'W/mK',
  heat_generation: 'W/m³',
  modulus: 'GPa',
  activation_energy: 'kJ/mol',
  rate_constant: '1/s',
  temperature_delta: 'K',
  inverse_time: '1/s',
}

/** 模块级单位符号映射缓存：{ [dimension]: symbol } */
const _unitSymbolMap = ref({})
let _unitSymbolsLoaded = false
let _unitSymbolsLoading = null

/**
 * 加载所有维度的首选单位符号到缓存
 * @returns {Promise<Record<string, string>>} dimension → symbol 映射
 */
export async function loadUnitSymbols() {
  if (_unitSymbolsLoaded) return _unitSymbolMap.value
  if (_unitSymbolsLoading) return _unitSymbolsLoading

  _unitSymbolsLoading = (async () => {
    const result = {}
    try {
      // 一次拉取全部单位主数据（dimension 为空即返回全部），
      // 避免并行发起 20+ 个按维度请求，防止浏览器中断产生 ERR_ABORTED 日志。
      const data = await mdmApi.listUnits()
      const list = Array.isArray(data) ? data : (data?.units || [])
      for (const dim of Object.keys(PREFERRED_UNIT_CODE)) {
        const preferred = list.find(
          (u) => u.dimension === dim && u.unit_code === PREFERRED_UNIT_CODE[dim] && u.is_active,
        )
        // 温度特殊处理：MDM symbol 为 "C"，显示为 "°C"
        result[dim] = preferred?.symbol
          ? (dim === 'temperature' ? '°C' : preferred.symbol)
          : FALLBACK_SYMBOL[dim]
      }
    } catch {
      // 拉取失败则整体回退到默认符号
      for (const dim of Object.keys(FALLBACK_SYMBOL)) {
        result[dim] = FALLBACK_SYMBOL[dim]
      }
    }
    _unitSymbolMap.value = result
    _unitSymbolsLoaded = true
    _unitSymbolsLoading = null
    return result
  })()
  return _unitSymbolsLoading
}

/**
 * 获取指定维度的首选单位符号（同步，需先调用 loadUnitSymbols）
 * @param {string} dimension - mass/volume/temperature/time/conductivity/voltage/energy/density/...
 * @returns {string} 单位符号，如 "kg"、"°C"、"h"
 */
export function getUnitSymbol(dimension) {
  return _unitSymbolMap.value[dimension] || FALLBACK_SYMBOL[dimension] || ''
}

/**
 * 单位符号 composable：返回响应式映射 + 加载函数
 * 用法：
 *   const { symbols, load } = useUnitSymbols()
 *   await load()
 *   symbols.mass  // "kg"
 */
export function useUnitSymbols() {
  return {
    symbols: _unitSymbolMap,
    load: loadUnitSymbols,
    get: getUnitSymbol,
  }
}

// ──────────────────────────────────────────────────────────────
// 属性→单位映射：从 MDM 特性主数据加载 property_name → {default_unit, units}
// 一次性加载所有属性的对应单位，供表单中"属性名→单位"自动联动使用
// ──────────────────────────────────────────────────────────────

/** 模块级属性-单位映射缓存：{ [property_name]: { default_unit, units } } */
const _propertyUnitMap = ref({})
let _propertyUnitsLoaded = false
let _propertyUnitsLoading = null

/**
 * 加载所有特性的属性-单位映射到缓存
 * @returns {Promise<Record<string, {default_unit: string, units: string[]}>>}
 */
export async function loadPropertyUnits() {
  if (_propertyUnitsLoaded) return _propertyUnitMap.value
  if (_propertyUnitsLoading) return _propertyUnitsLoading

  _propertyUnitsLoading = (async () => {
    const result = {}
    try {
      const data = await mdmApi.listPropertiesWithUnits()
      const list = Array.isArray(data) ? data : (data?.properties || [])
      for (const p of list) {
        const name = (p.property_name || '').trim()
        if (!name) continue
        result[name] = {
          default_unit: p.default_unit || '',
          units: Array.isArray(p.units) ? p.units.filter(Boolean) : [],
        }
      }
    } catch (e) {
      console.warn('加载 MDM 属性-单位映射失败:', e)
    }
    _propertyUnitMap.value = result
    _propertyUnitsLoaded = true
    _propertyUnitsLoading = null
    return result
  })()
  return _propertyUnitsLoading
}

/**
 * 获取指定属性名的可选单位列表（同步，需先调用 loadPropertyUnits）
 * @param {string} name 属性名
 * @returns {string[]}
 */
export function getPropertyUnits(name) {
  return _propertyUnitMap.value[name]?.units || []
}

/**
 * 获取指定属性名的默认单位（同步，需先调用 loadPropertyUnits）
 * @param {string} name 属性名
 * @returns {string}
 */
export function getPropertyDefaultUnit(name) {
  return _propertyUnitMap.value[name]?.default_unit || ''
}

/**
 * 属性-单位 composable：返回响应式映射 + 加载函数 + 查询函数
 * 用法：
 *   const { map, load, getUnits, getDefaultUnit } = usePropertyUnits()
 *   await load()
 *   getDefaultUnit('ionic_conductivity')  // "S/cm"
 */
export function usePropertyUnits() {
  return {
    map: _propertyUnitMap,
    load: loadPropertyUnits,
    getUnits: getPropertyUnits,
    getDefaultUnit: getPropertyDefaultUnit,
  }
}

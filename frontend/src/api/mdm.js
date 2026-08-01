import client from './client'

// ──────────────────────────────────────────────────────────────
// P1 参考字典中心
// ──────────────────────────────────────────────────────────────
export const listStatusCodes = (domain = '') => client.get('/mdm/status-codes', { params: { domain } })
export const getStatusCode = (domain, code) => client.get(`/mdm/status-codes/${encodeURIComponent(domain)}/${encodeURIComponent(code)}`)

export const listClassifications = (domain = '', parentCode = '') =>
  client.get('/mdm/classifications', { params: { domain, parent_code: parentCode } })
export const getClassification = (code) => client.get(`/mdm/classifications/${encodeURIComponent(code)}`)

export const listUnits = (dimension = '') => client.get('/mdm/units', { params: { dimension } })
export const getUnit = (unitCode) => client.get(`/mdm/units/${encodeURIComponent(unitCode)}`)

// ── 单位版本管理（T-018 / T-019）─────────────────────────────
export const listUnitVersions = (unitCode) =>
  client.get(`/mdm/units/${encodeURIComponent(unitCode)}/versions`)
export const getUnitVersion = (unitCode, versionId) =>
  client.get(`/mdm/units/${encodeURIComponent(unitCode)}/versions/${encodeURIComponent(versionId)}`)
export const activateUnitVersion = (unitCode, versionId) =>
  client.post(`/mdm/units/${encodeURIComponent(unitCode)}/versions/${encodeURIComponent(versionId)}/activate`)
export const compareUnitVersions = (unitCode, v1, v2) =>
  client.get(`/mdm/units/${encodeURIComponent(unitCode)}/versions/compare`, { params: { v1, v2 } })

export const listUnitConversions = (fromUnit = '') =>
  client.get('/mdm/unit-conversions', { params: { from_unit: fromUnit } })
export const convertUnit = (value, fromUnit, toUnit) =>
  client.post('/mdm/units/convert', { value, from_unit: fromUnit, to_unit: toUnit })

export const listStandards = () => client.get('/mdm/standards')
export const getStandard = (standardCode) => client.get(`/mdm/standards/${encodeURIComponent(standardCode)}`)

export const listGhsClasses = () => client.get('/mdm/ghs-classes')

export const listDimensions = (domain = '') => client.get('/mdm/dimensions', { params: { domain } })
export const getDimension = (domain, code) =>
  client.get(`/mdm/dimensions/${encodeURIComponent(domain)}/${encodeURIComponent(code)}`)

// ──────────────────────────────────────────────────────────────
// P2 物料/样品类型/设备模板/位置
// ──────────────────────────────────────────────────────────────
export const listSampleTypes = () => client.get('/mdm/sample-types')
export const getSampleType = (typeCode) => client.get(`/mdm/sample-types/${encodeURIComponent(typeCode)}`)

export const listSampleStatusTransitions = () => client.get('/mdm/sample-status-transitions')
export const checkSampleTransition = (fromStatus, toStatus) =>
  client.get('/mdm/sample-status-transitions/check', { params: { from_status: fromStatus, to_status: toStatus } })

export const listLocations = (parentCode = '') => client.get('/mdm/locations', { params: { parent_code: parentCode } })
export const getLocation = (locationId) => client.get(`/mdm/locations/${encodeURIComponent(locationId)}`)
export const getLocationTree = (locationId) => client.get(`/mdm/locations/${encodeURIComponent(locationId)}/tree`)

export const listContainers = () => client.get('/mdm/containers')
export const getContainer = (containerCode) => client.get(`/mdm/containers/${encodeURIComponent(containerCode)}`)

export const listLogisticsTypes = () => client.get('/mdm/logistics-types')

export const listEquipmentTemplates = () => client.get('/mdm/equipment-templates')
export const getEquipmentTemplate = (templateCode) =>
  client.get(`/mdm/equipment-templates/${encodeURIComponent(templateCode)}`)
export const getEquipmentTemplateCapabilities = (templateCode) =>
  client.get(`/mdm/equipment-templates/${encodeURIComponent(templateCode)}/capabilities`)

export const listEquipmentCapabilities = () => client.get('/mdm/equipment-capabilities')
export const getEquipmentCapability = (capabilityCode) =>
  client.get(`/mdm/equipment-capabilities/${encodeURIComponent(capabilityCode)}`)

export const listMaterialCategories = (parentCode = '') =>
  client.get('/mdm/material-categories', { params: { parent_code: parentCode } })
export const getMaterialCategory = (categoryCode) =>
  client.get(`/mdm/material-categories/${encodeURIComponent(categoryCode)}`)

// ──────────────────────────────────────────────────────────────
// P3 CIMC（特性-指标-方法-能力）
// ──────────────────────────────────────────────────────────────
export const listProperties = () => client.get('/mdm/properties')
export const getProperty = (propertyId) => client.get(`/mdm/properties/${encodeURIComponent(propertyId)}`)
export const listPropertiesWithUnits = () => client.get('/mdm/properties-with-units')

export const listTestMethods = () => client.get('/mdm/test-methods')
export const getTestMethod = (methodId) => client.get(`/mdm/test-methods/${encodeURIComponent(methodId)}`)

export const listTestItems = () => client.get('/mdm/test-items')
export const getTestItem = (itemId) => client.get(`/mdm/test-items/${encodeURIComponent(itemId)}`)

export const listSpecifications = () => client.get('/mdm/specifications')
export const getSpecification = (specId) => client.get(`/mdm/specifications/${encodeURIComponent(specId)}`)

export const listInspectionCapabilities = () => client.get('/mdm/inspection-capabilities')
export const getInspectionCapability = (capabilityId) =>
  client.get(`/mdm/inspection-capabilities/${encodeURIComponent(capabilityId)}`)

// ──────────────────────────────────────────────────────────────
// P4 工艺路线
// ──────────────────────────────────────────────────────────────
export const listProcessRoutes = () => client.get('/mdm/process-routes')
export const getProcessRoute = (routeId) => client.get(`/mdm/process-routes/${encodeURIComponent(routeId)}`)
export const getProcessRouteSteps = (routeId) =>
  client.get(`/mdm/process-routes/${encodeURIComponent(routeId)}/steps`)

export const listProcessSteps = () => client.get('/mdm/process-steps')
export const getProcessStep = (stepId) => client.get(`/mdm/process-steps/${encodeURIComponent(stepId)}`)
export const getProcessStepParameters = (stepId) =>
  client.get(`/mdm/process-steps/${encodeURIComponent(stepId)}/parameters`)
export const getProcessStepEquipmentTemplates = (stepId) =>
  client.get(`/mdm/process-steps/${encodeURIComponent(stepId)}/equipment-templates`)

export const listProcessParameters = () => client.get('/mdm/process-parameters')
export const getProcessParameter = (parameterId) =>
  client.get(`/mdm/process-parameters/${encodeURIComponent(parameterId)}`)

// ──────────────────────────────────────────────────────────────
// P5 文档版本与执行快照
// ──────────────────────────────────────────────────────────────
export const listDocuments = (documentType = '') =>
  client.get('/mdm/documents', { params: { document_type: documentType } })
export const getDocument = (documentId) => client.get(`/mdm/documents/${encodeURIComponent(documentId)}`)
export const getDocumentVersions = (documentId) =>
  client.get(`/mdm/documents/${encodeURIComponent(documentId)}/versions`)
export const getDocumentVersion = (versionId) =>
  client.get(`/mdm/document-versions/${encodeURIComponent(versionId)}`)
export const getOrderSnapshot = (snapshotId) => client.get(`/mdm/order-snapshots/${encodeURIComponent(snapshotId)}`)

// ──────────────────────────────────────────────────────────────
// 通用：新增 + 启用/停用
// ──────────────────────────────────────────────────────────────
/**
 * 新增主数据记录。
 * @param domain 主数据域（如 status-codes / classifications / units / ...）
 * @param payload 字段字典（按表结构提交，自动生成字段由后端填充）
 */
export const createItem = (domain, payload) =>
  client.post(`/mdm/${domain}`, payload)

/**
 * 切换启用/停用状态。
 * @param domain 主数据域
 * @param pkPath 主键路径段（单列主键直接传 code；复合主键用 / 拼接，如 "sample/in_progress"）
 * @param isActive 目标状态
 */
export const toggleActive = (domain, pkPath, isActive) =>
  client.patch(`/mdm/${domain}/${pkPath}/active`, null, { params: { is_active: isActive } })

